from pydantic import Field
from typing import Dict, Iterator, Tuple, Type, Union

from ipyelk.elements import (
    Partition,
    Port,
    SymbolSpec,
    merge_excluded,
)
from ipyelk.elements.index import iter_hierarchy

from .parts import Part
from .relationships import DirectedAssociation, Relationship
from .symbols import (
    make_arrow_symbol,
    make_containment_symbol,
    make_feature_typing_symbol,
    make_redefinition_symbol,
    make_rhombus_symbol,
    make_subsetting_symbol,
)


class PartDiagram(Partition):
    """A SysML 2 Part Diagram, based on the IPyELK BlockDiagram."""

    class Config:
        copy_on_model_validation = False
        excluded = merge_excluded(Partition, "symbols", "style")

    default_edge: Type[Relationship] = Field(default=DirectedAssociation)

    symbols: SymbolSpec = SymbolSpec().add(
        make_arrow_symbol(identifier="generalization", r=8, closed=True),
        make_arrow_symbol(identifier="directed_association", r=8, closed=False),
        make_containment_symbol(identifier="containment", r=8),
        make_feature_typing_symbol(identifier="feature_typing", r=8),
        make_redefinition_symbol(identifier="redefinition", r=8),
        make_subsetting_symbol(identifier="subsetting", r=8),
        make_rhombus_symbol(identifier="composition", r=8),
        make_rhombus_symbol(identifier="aggregation", r=8),
    )

    style: Dict[str, Dict] = {
        # Elk Label styles for Box Titles
        " .elklabel.compartment_title_1": {
            "font-style": "normal",
            "font-weight": "bold",
        },
        " .elklabel.compartment_title_2": {
            "font-style": "normal",
            "font-weight": "normal",
        },
        # Style Arrowheads (future may try to )
        "symbol.subsetting ellipse": {
            "fill": "var(--jp-elk-node-stroke)",
        },
        "symbol.feature_typing ellipse": {
            "fill": "var(--jp-elk-node-stroke)",
        },
        " .internal > .elknode": {
            "stroke": "transparent",
            "fill": "transparent",
        },
        # Necessary for having the viewport use the whole vertical height
        " .lm-Widget.jp-ElkView .sprotty > .sprotty-root > svg.sprotty-graph": {
            "height": "unset!important",
        },
        " .dashed.elkedge > path ": {
            "stroke-dasharray": "3 3",
        },
        " text.elklabel.node_type_label": {
            "font-style": "italic",
        },
    }

    @property
    def all_parts(self) -> Iterator[Tuple[Part, Relationship]]:
        """Iterate over BaseElements that follow the `Part` hierarchy
        and return nodes and their parent
        """
        for parent, element in iter_hierarchy(self, types=(Part,)):
            if isinstance(element, Part):
                yield parent, element

    @property
    def all_relationships(self) -> Iterator[Tuple[Union[Part, "PartDiagram"], Relationship]]:
        """Iterate over BaseElements that follow the `Part` hierarchy
        and return edges and their parent
        """
        for parent, element in iter_hierarchy(self, types=(Relationship,)):
            if isinstance(element, Relationship):
                yield parent, element

    def clear_all_relationships(self):
        for node in self.all_parts:
            node.edges = []

    def add_relationship(
        self,
        source: Union[Part, Port],
        target: Union[Part, Port],
        cls: Type[Relationship] = Relationship,
        data: dict = None,
    ) -> Relationship:
        data = data or {}
        relationship = cls(source=source, target=target, data=data)
        self.edges.append(relationship)
        return relationship
