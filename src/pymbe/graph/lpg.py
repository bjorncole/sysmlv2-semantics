import traceback

from functools import lru_cache
from pathlib import Path
from uuid import uuid4
from warnings import warn

from ruamel.yaml import YAML

import networkx as nx
import traitlets as trt
import typing as ty

from ..model import Element, Model


yaml = YAML(typ="unsafe", pure=True)


class SysML2LabeledPropertyGraph(trt.HasTraits):
    """A Labelled Property Graph for SysML v2.

    ..todo::
        Integrate it with the RDF representation.
    """

    FILTERED_DATA_KEYS: tuple = ("@context",)
    ATTRIBUTE_TO_EDGES: tuple = (
        # Adds additional relationships (edges) based on element attributes
        # dict(attribute="owner", metatype="Owned", reversed=True),
    )
    IMPLIED_GENERATORS: dict = {
        # Adds additional implied edges based on a tuple of generators
        "ImpliedFeedforwardEdges": "get_implied_feedforward_edges",
    }
    sysml_projections: dict = trt.Dict()

    model: Model = trt.Instance(Model, allow_none=True)
    graph: nx.MultiDiGraph = trt.Instance(nx.MultiDiGraph, args=tuple())

    max_graph_size: int = trt.Int(default_value=256)
    merge: bool = trt.Bool(default_value=False)

    nodes: dict = trt.Dict()
    edges: dict = trt.Dict()

    node_types: tuple = trt.Tuple()
    edge_types: tuple = trt.Tuple()

    nodes_by_type: dict = trt.Dict()
    edges_by_type: dict = trt.Dict()

    def __repr__(self):
        return (
            "<SysML v2 LPG: "
            f"{len(self.graph.nodes):,d} nodes, "
            f"{len(self.graph.edges):,d} edges"
            ">"
        )

    def __getitem__(self, *args):
        return self.graph.__getitem__(*args)

    @trt.observe("graph", "max_graph_size")
    def _update_projections(self, *_):
        projections = yaml.load(
            stream=(Path(__file__).parent / "sysml_subgraphs.yml").read_text(),
        )
        # TODO: Look into filtering the other projections
        if len(self.graph) > self.max_graph_size:
            projections.pop("Complete", None)

        self.sysml_projections = dict(projections)

    @staticmethod
    def _make_nx_multi_edge(source, target, metatype, **data):
        return (
            source,                           # source
            target,                           # target
            metatype,                         # edge type
            {                                 # edge data
                "@id": f"_{uuid4()}",
                "@type": metatype,
                "relatedElement": [
                    {"@id": source},
                    {"@id": target},
                ],
                "source": [{"@id": source}],
                "target": [{"@id": target}],
                **data
            },
        )

    @trt.observe("model")
    def update(self, change: trt.Bunch):
        self._adapt.cache_clear()

        model = change.new
        if not isinstance(model, Model):
            return

        all_relationships: ty.Set[Element] = set(model.all_relationships.values())

        # Draw as edges all non-abstract relationships
        graph_relationships: ty.Set[Element] = {
            relationship
            for relationship in all_relationships
            if "isAbstract" not in relationship._data
        }
        # And everything else is a node
        graph_elements: ty.Set[Element] = set(model.elements.values()).difference(graph_relationships)

        # Add the abstract_relationships edges we removed from relationships
        expanded_relationships: ty.Set[Element] = all_relationships.difference(graph_relationships)
        edges_from_abstract_relationships = [
            [
                relationship._id,
                related_element_entry["@id"],
                f"""{relationship._metatype}End""",
                {
                    "@id": f"{relationship._id}_{endpt_index}",
                    "@type": f"""{relationship._metatype}End""",
                    "RelationshipType": True,
                },
            ]
            for relationship in expanded_relationships
            for endpt_index, related_element_entry in enumerate(relationship._data["relatedElement"])
        ]

        graph = nx.MultiDiGraph()
        if self.merge:
            graph.add_nodes_from(self.graph)
            graph.add_edges_from(self.graph)

        old_graph = self.graph
        del old_graph

        graph.add_nodes_from(
            {
                element._id: element._data
                for element in graph_elements
            }.items()
        )

        graph.add_edges_from([
            [
                source._id,              # source node (str id)
                target._id,              # target node (str id)
                relationship._metatype,  # edge metatype (str name)
                relationship._data,      # edge data (dict)
            ]
            for relationship in graph_relationships
            for source in relationship.source
            for target in relationship.target
        ] + edges_from_abstract_relationships)

        with self.hold_trait_notifications():
            self.nodes = dict(graph.nodes)
            self.edges = dict(graph.edges)

            self.node_types = tuple(sorted({
                node["@type"]
                for node in self.nodes.values()
                if "@type" in node
            }))
            self.edge_types = tuple(sorted({
                edge["@type"]
                for edge in self.edges.values()
                if "@type" in edge
            }))

            self.nodes_by_type = {
                node_type: [
                    node
                    for node in graph.nodes
                    if graph.nodes[node].get("@type") == node_type
                ]
                for node_type in self.node_types
            }
            self.edges_by_type = {
                edge_type: [
                    edge
                    for edge in graph.edges
                    if edge[2] == edge_type
                ]
                for edge_type in self.edge_types
            }

            self.graph = graph

    def get_projection_instructions(self, projection: str) -> dict:
        instructions = {**self.sysml_projections.get(projection, {})}
        if not instructions:
            raise ValueError(
                f"Could not find SysML Project: '{projection}'.\n"
                f"Options available are: {tuple(self.sysml_projections)}"
            )

        for key in tuple(instructions):
            # revert included for excluded types
            if key.startswith("included_") and key.endswith("_types"):
                included_types = instructions.pop(key)
                types_key = key.replace("included_", "")
                types = set(getattr(self, types_key)).difference(included_types)
                instructions[f"excluded_{types_key}"] = tuple(sorted(types))

        function_attributes = self.adapt.__annotations__
        return {
            key: value
            for key, value in instructions.items()
            if key in function_attributes
        }

    def get_implied_feedforward_edges(self) -> list:
        eeg = self.get_projection("Expression Evaluation")

        edge_dict = {
            edge["@id"]: edge
            for edge in self.edges.values()
        }
        return_parameter_memberships = [
            self.edges[(source, target, kind)]
            for source, target, kind in self.edges
            if kind == "ReturnParameterMembership"
        ]
        feature_values = [
            self.edges[(source, target, kind)]
            for source, target, kind in self.edges
            if kind == "FeatureValue"
        ]

        implied_edges = []

        for feature_value in feature_values:
            att_usage, expr = feature_value["owningRelatedElement"]["@id"], feature_value["value"]["@id"]
            expr_result_id = self.nodes[expr]["result"]["@id"]

            implied_edges += [(
                expr_result_id,
                att_usage,
                "ImpliedParameterFeedforward",
            )]

        for membership in return_parameter_memberships:
            for result_feeder_id in eeg.predecessors(membership["memberElement"]["@id"]):
                result_feeder = self.nodes[result_feeder_id]
                rf_metatype = result_feeder["@type"]

                # we only want Expressions that have at least one input parameter
                if "Expression" not in rf_metatype or rf_metatype in ("FeatureReferenceExpression"):
                    if rf_metatype == "FeatureReferenceExpression":
                        implied_edges += [
                            (
                                result_feeder["referent"]["@id"],
                                result_feeder_id,
                                "ImpliedReferentFeed"
                            )
                        ]
                    continue

                # Path Step Expressions need results fed into them, so add edges to order this
                # FIXME: Super jenky because we are avoiding the first element to prevent a cycle .. first arg does feed in properly
                if rf_metatype == "PathStepExpression":
                    arg_ids = result_feeder["argument"]
                    results = [
                        self.nodes[arg_id["@id"]]["result"]["@id"]
                        for index, arg_id in enumerate(arg_ids) if index > 0
                    ]

                    implied_edges += [
                        (result, result_feeder_id, "ImpliedPathArgumentFeedforward")
                        for result in results
                    ]

                expr_results = []
                expr_members, para_members, result_members = [], [], []
                # assume that the members of an expression that are themselves members are
                # referenced in the same order as parameters - results of an expression
                # should feed into the input parameter owned by its owner

                owned_memberships = result_feeder["ownedMembership"]

                # NOTE: There is a special case for when there is a ResultExpressionMembership:
                # A ResultExpressionMembership is a FeatureMembership that indicates that the
                # ownedResultExpression provides the result values for the Function or Expression
                # that owns it. The owning Function or Expression must contain a BindingConnector
                # between the result parameter of the ownedResultExpression and the result
                # parameter of the Function or Expression.
                rem_flag = False
                for om_id in owned_memberships:
                    relationship = edge_dict[om_id["@id"]]
                    relationship_metatype = relationship["@type"]
                    edge_member_id = relationship["memberElement"]["@id"]
                    if "Parameter" in relationship_metatype:
                        if "ReturnParameter" in relationship_metatype:
                            result_members.append(edge_member_id)
                        else:
                            para_members.append(edge_member_id)
                    elif "Result" in relationship_metatype:
                        rem_owning_type = self.nodes[relationship["owningType"]["@id"]]
                        rem_owned_ele = self.nodes[relationship["ownedMemberElement"]["@id"]]
                        rem_flag = True
                    elif "Membership" in relationship_metatype:
                        edge_member = relationship["memberElement"]["@id"]
                        expr_members.append(edge_member)
                        if "result" in self.nodes[edge_member]:
                            expr_result = self.nodes[edge_member]["result"]["@id"]
                            expr_results.append(expr_result)

                # FIXME: streamline / simplify this
                if rem_flag:
                    rem_cheat_expr = rem_owned_ele["@id"]
                    rem_cheat_result = rem_owned_ele["result"]["@id"]
                    rem_cheat_para = rem_owning_type["result"]["@id"]

                    expr_members = [rem_cheat_expr]
                    expr_results = [rem_cheat_result]
                    para_members = [rem_cheat_para]

                implied_edges += [
                    (expr_results[index], para_members[index], "ImpliedParameterFeedforward")
                    for index, expr in enumerate(expr_members)
                    if index < len(expr_results) and index < len(para_members)
                ]

        return implied_edges

    def get_implied_edges(self, *implied_edge_types):
        new_edges = []
        for implied_edge_type in implied_edge_types:
            function_name = self.IMPLIED_GENERATORS.get(implied_edge_type)
            if function_name is None:
                warn(f"'{implied_edge_type}' is not a valid edge generator!")
                continue
            edge_generator = getattr(self, function_name, None)
            if edge_generator is None:
                raise SystemError(f"Could not find '{function_name}' implied edge generator!")
            new_edges += [
                self._make_nx_multi_edge(source, target, metatype, label=metatype)
                for source, target, metatype in edge_generator()
            ]
        return new_edges

    def get_projection(self, projection: str) -> nx.Graph:
        return self.adapt(**self.get_projection_instructions(
            projection=projection,
        ))

    def adapt(self,
        excluded_node_types: ty.Union[list, set, tuple] = None,
        excluded_edge_types: ty.Union[list, set, tuple] = None,
        reversed_edge_types: ty.Union[list, set, tuple] = None,
        implied_edge_types: ty.Union[list, set, tuple] = None,
    ) -> ty.Union[nx.Graph, nx.DiGraph]:
        """
            Using the existing graph, filter by node and edge types, and/or
            reverse certain edge types.
        """
        excluded_edge_types = excluded_edge_types or []
        excluded_node_types = excluded_node_types or []
        reversed_edge_types = reversed_edge_types or []
        implied_edge_types = implied_edge_types or []

        # NOTE: Sorting into a tuple to make the LRU Cache work
        return self._adapt(
            excluded_edge_types=tuple(sorted(excluded_edge_types)),
            excluded_node_types=tuple(sorted(excluded_node_types)),
            reversed_edge_types=tuple(sorted(reversed_edge_types)),
            implied_edge_types=tuple(sorted(implied_edge_types)),
        ).copy()

    @lru_cache
    def _adapt(self,
        excluded_node_types: ty.Union[list, set, tuple] = None,
        excluded_edge_types: ty.Union[list, set, tuple] = None,
        reversed_edge_types: ty.Union[list, set, tuple] = None,
        implied_edge_types: ty.Union[list, set, tuple] = None,
    ) -> nx.Graph:
        graph = self.graph.copy()
        new_edges = self.get_implied_edges(*implied_edge_types)
        if new_edges:
            graph.add_edges_from(new_edges)

        mismatched_node_types = set(excluded_node_types).difference(self.node_types)
        if mismatched_node_types:
            print(f"These node types are not in the graph: {mismatched_node_types}.")

        mismatched_edge_types = {
            *excluded_edge_types,
            *reversed_edge_types,
        }.difference(self.edge_types)
        if mismatched_edge_types:
            print(f"These edge types are not in the graph: {mismatched_edge_types}.")

        included_nodes = sum(
            [
                nodes
                for node_type, nodes in self.nodes_by_type.items()
                if node_type not in excluded_node_types
            ],
            [],
        )
        subgraph = graph.__class__(graph.subgraph(included_nodes))

        def _process_edge(src, tgt, typ, data, rev_types):
            data = {**self.graph.edges.get((src, tgt, typ), {}), **data}
            if typ in rev_types:
                tgt, src = src, tgt
                typ += "^-1"
                data["@type"] = typ
            return src, tgt, typ, data

        edges = [
            _process_edge(src, tgt, typ, data, reversed_edge_types)
            for (src, tgt, typ), data in subgraph.edges.items()
            if typ not in excluded_edge_types
        ]

        new_graph = graph.__class__()
        new_graph.add_edges_from(edges)
        new_graph.update(nodes={
            node: self.graph.nodes.get(node)
            for node in new_graph.nodes
        }.items())
        return new_graph

    @staticmethod
    def _make_undirected(graph):
        if graph.is_multigraph():
            return nx.MultiGraph(graph)
        else:
            return nx.Graph(graph)

    def get_path_graph(
        self,
        graph: nx.Graph,
        source: str,
        target: str,
        enforce_directionality: bool = True,
        try_reverse: bool = True,
    ):
        """Make a new graph with the shortest paths between two nodes"""
        new_graph = graph if enforce_directionality else self._make_undirected(graph)
        try:
            nodes = set(sum(map(
                list,
                nx.all_shortest_paths(new_graph, source, target)
            ), []))
            return graph.__class__(graph.subgraph(nodes))

        except (nx.NetworkXError, nx.NetworkXException) as exc:
            warn(traceback.format_exc())
            if try_reverse:
                return self.get_path_graph(
                    graph=graph,
                    source=target,
                    target=source,
                    enforce_directionality=enforce_directionality,
                    try_reverse=False,
                )
            return graph.__class__()

    def get_spanning_graph(
        self,
        graph: nx.Graph,
        seeds: ty.Union[list, set, tuple],
        max_distance: int = 2,
        enforce_directionality: bool = True,
    ):
        if not enforce_directionality:
            graph = self._make_undirected(graph)
        seed_nodes = {
            id_: max_distance
            for id_ in seeds
            if id_ in graph.nodes
        }
        seed_elements = [
            self.model.elements[id_]
            for id_ in seeds
            if id_ not in seed_nodes
            and id_ in self.model.elements
        ]
        seed_edges = [
            (element.source, element.target)
            for element in seed_elements
            if element._is_relationship
        ]

        distances = {
            node: max_distance - 1
            for node in set(sum(seed_edges, []))
            if node in graph
        }
        distances.update(seed_nodes)

        max_iter = 100
        while sum(distances.values()) > 0 and max_iter > 0:
            max_iter -= 1
            for node_id, distance in tuple(distances.items()):
                if distance < 1:
                    continue
                for neighbor in graph.neighbors(node_id):
                    distances[neighbor] = distances.get(neighbor, distance - 1)
                distances[node_id] -= 1

        nodes = tuple(distances)

        return graph.__class__(graph.subgraph(nodes))
