import json

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Union
from uuid import uuid4
from warnings import warn


VALUE_METATYPES = ("AttributeDefinition", "AttributeUsage", "DataType")


class ListOfNamedItems(list):
    """A list that also can return items by their name."""

    # FIXME: figure out why __dir__ of returned objects think they are lists
    def __getitem__(self, key):
        item_map = {
            item._data["name"]: item
            for item in self
            if isinstance(item, Element)
            and "name" in item._data
        }
        if key in item_map:
            return item_map[key]
        return super().__getitem__(key)


class Naming(Enum):
    """An enumeration for how to repr SysML elements"""

    identifier = "IDENTIFIER"
    long = "LONG"
    qualified = "QUALIFIED"
    short = "SHORT"

    def get_name(self, element: "Element") -> str:
        naming = self._value_

        # TODO: Check with Bjorn, he wanted: (a)-[r:RELTYPE {name: a.name + '<->' + b.name}]->(b)
        if element._is_relationship:
            return (
                f"<{element._metatype}({element.source} ←→ {element.target})>"
            )

        data = element._data
        if naming == Naming.qualified:
            return f"""<{data["qualifiedName"]}>"""

        if naming == Naming.identifier:
            return f"""<{data["@id"]}>"""

        name = data.get("name") or data["@id"]
        if naming == Naming.short:
            return f"<{name}>"
        else:
            return f"""<{name} «{data["@type"]}»>"""


@dataclass(repr=False)
class Model:
    """A SysML v2 Model"""

    # TODO: Look into making elements immutable (e.g., frozen dict)
    elements: Dict[str, "Element"]

    name: str = "SysML v2 Model"

    all_relationships: Dict[str, "Element"] = field(default_factory=dict)
    all_non_relationships: Dict[str, "Element"] = field(default_factory=dict)

    ownedElement: ListOfNamedItems = field(default_factory=ListOfNamedItems)
    ownedMetatype: Dict[str, List["Element"]] = field(default_factory=dict)
    ownedRelationship: List["Element"] = field(default_factory=list)

    source: Any = None

    _naming: Naming = Naming.long  # The scheme to use for repr'ing the elements

    def __post_init__(self):
        self.elements = {
            id_: Element(_data=data, _model=self)
            for id_, data in self.elements.items()
            if isinstance(data, dict)
        }

        self._add_owned()

        # Modify and add derived data to the elements
        self._add_relationships()
        self._add_labels()

    def __repr__(self) -> str:
        data = self.source or f"{len(self.elements)} elements"
        return f"<SysML v2 Model ({data})>"

    @staticmethod
    def load(
        elements: Union[List[Dict], Set[Dict], Tuple[Dict]],
        **kwargs,
    ) -> "Model":
        """Make a Model from an iterable container of elements"""
        return Model(
            elements={
                element["@id"]: element
                for element in elements
            },
            **kwargs,
        )

    @staticmethod
    def load_from_file(filepath: Union[Path, str]) -> "Model":
        """Make a model from a JSON file"""
        if isinstance(filepath, str):
            filepath = Path(filepath)

        if not filepath.is_file():
            raise ValueError(f"'{filepath}' does not exist!")

        return Model.load(
            elements=json.loads(filepath.read_text()),
            name=filepath.name,
            source=filepath.resolve(),
        )

    def save_to_file(self, filepath: Union[Path, str], indent: int = 2) -> bool:
        if isinstance(filepath, str):
            filepath = Path(filepath)
        filepath.write_text(
            json.dumps(
                [element._data for element in self.elements.values()],
                indent=indent,
            ),
        )

    def _add_labels(self):
        """Attempts to add a label to the elements"""
        from .label import get_label
        for element in self.elements.values():
            label = get_label(element=element)
            if label:
                element._derived["label"] = label

    def _add_owned(self):
        """Adds owned elements, relationships, and metatypes to the model"""
        elements = self.elements

        self.all_relationships = {
            id_: element
            for id_, element in elements.items()
            if element._is_relationship
        }
        self.all_non_relationships = {
            id_: element
            for id_, element in elements.items()
            if not element._is_relationship
        }

        owned = [
            element
            for element in elements.values()
            if element.get_owner() is None
        ]
        self.ownedElement = ListOfNamedItems(
            element
            for element in owned
            if not element._is_relationship
        )

        self.ownedRelationship = [
            relationship
            for relationship in owned
            if relationship._is_relationship
        ]

        by_metatype = defaultdict(list)
        for element in elements.values():
            by_metatype[element._metatype].append(element)
        self.ownedMetatype = dict(by_metatype)

    def _add_relationships(self):
        """Adds relationships to elements"""
        relationship_mapper = {
            "through": ("source", "target"),
            "reverse": ("target", "source"),
        }
        # TODO: make this more elegant...  maybe.
        for relationship in self.all_relationships.values():
            endpoints = {
                endpoint_type: [
                    self.elements[endpoint["@id"]]
                    for endpoint in relationship._data[endpoint_type]
                ]
                for endpoint_type in ("source", "target")
            }
            metatype = relationship._metatype
            for direction, (key1, key2) in relationship_mapper.items():
                endpts1, endpts2 = endpoints[key1], endpoints[key2]
                for endpt1 in endpts1:
                    for endpt2 in endpts2:
                        endpt1._derived[f"{direction}{metatype}"] += [
                            {"@id": endpt2._data["@id"]}
                        ]


@dataclass(repr=False)
class Element:
    """A SysML v2 Element"""

    _data: dict
    _model: Model

    _id: str = field(default_factory=lambda: str(uuid4()))
    _metatype: str = "Element"
    _derived: Dict[str, List] = field(default_factory=lambda: defaultdict(list))
    _instances: List["Instance"] = field(default_factory=list)
    _is_abstract: bool = False
    _is_relationship: bool = False

    def __post_init__(self):
        self._id = self._data["@id"]
        self._metatype = self._data["@type"]
        self._is_abstract = bool(self._data.get("isAbstract"))
        self._is_relationship = "relatedElement" in self._data
        for key, items in self._data.items():
            if key.startswith("owned") and isinstance(items, list):
                self._data[key] = ListOfNamedItems(items)

    def __call__(self, *args, **kwargs):
        if self._metatype in VALUE_METATYPES:
            return ValueHolder(*args, **kwargs, element=self)
        return Instance(*args, **kwargs, element=self)

    def __dir__(self):
        return sorted(set(
            list(super().__dir__()) + [
                key
                for key in [*self._data, *self._derived]
                if key.isidentifier()
            ]
        ))

    def __eq__(self, other):
        if isinstance(other, str):
            return self._id == other
        # TODO: Assess if this is more trouble than it's worth
        # if isinstance(other, dict):
        #     return tuple(sorted(self._data.items())) == tuple(sorted(other.items()))
        return self is other

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"Cannot find {key}")

    def __getitem__(self, key: str):
        found = False
        for source in ("_data", "_derived"):
            source = self.__getattribute__(source)
            if key in source:
                found = True
                item = source[key]
                break
        if not found:
            raise KeyError(f"No '{key}' in {self}")

        if isinstance(item, (dict, str)):
            item = self.__safe_dereference(item)
        elif isinstance(item, (list, tuple, set)):
            items = [
                self.__safe_dereference(subitem)
                for subitem in item
            ]
            return type(item)(items)
        return item

    def __hash__(self):
        return hash(self._data["@id"])

    def __repr__(self):
        return self._model._naming.get_name(element=self)

    @property
    def label(self) -> str:
        return self._derived.get("label")

    @property
    def relationships(self) -> Dict[str, Any]:
        return {
            key: self[key] for key in self._derived
            if key.startswith("through") or
            key.startswith("reverse")
        }

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def get_element(self, element_id) -> "Element":
        return self._model.elements.get(element_id)

    def get_owner(self) -> "Element":
        data = self._data
        owner_id = None
        for key in ("owner", "owningRelatedElement", "owningRelationship"):
            owner_id = (data.get(key) or {}).get("@id")
            if owner_id is not None:
                break
        if owner_id is None:
            return None
        return self._model.elements[owner_id]

    @staticmethod
    def new(data: dict, model: Model) -> "Element":
        return Element(_data=data, _model=model)

    def __safe_dereference(self, item):
        """If given a reference to another element, try to get that element"""
        try:
            if isinstance(item, dict) and "@id" in item:
                if len(item) > 1:
                    warn(f"Found a reference with more than one entry: {item}")
                item = item["@id"]
            return self._model.elements[item]
        except KeyError:
            return item


@dataclass
class Instance:
    """
    An M0 instantiation of an M1 element.

    Sequences of instances are intended to follow the mathematical base semantics of SysML v2.
    """

    element: Element
    name: str = ""

    def __post_init__(self):
        element = self.element
        if self not in element._instances:
            element._instances += [self]
        if not self.name:
            id_ = element._instances.index(self) + 1
            name = element.label or element._id
            self.name = f"{name}#{id_}"


@dataclass
class ValueHolder(Instance):
    """An M0 instantiation of a Value element"""

    value: Any = None

    def __repr__(self):
        value = self.value
        if value is None:
            value = "unset"
        return f"{self.name} ({value})"
