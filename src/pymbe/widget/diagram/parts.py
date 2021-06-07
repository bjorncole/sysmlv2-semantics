from pydantic import Field

from ipyelk.elements import Compartment, Record


class Part(Record):
    """A container for storing the data of a SysML 2 Part."""

    data: dict = Field(
        default_factory=dict,
        description="The data in the part.",
    )
    id: str = Field(default="")

    @staticmethod
    def make_property_label(item):
        label = f"""- {item["name"]}"""
        if "type" in item:
            label += f""" :: {item["type"]}"""
        return label

    @classmethod
    def from_data(cls, data: dict, width=220):
        id_ = data["@id"]
        label = (
                data.get("value")
                or data.get("label")
                or data.get("name")
                or id_
        )
        metatype = data.get("@type")

        if (
                metatype in ("MultiplicityRange",)
                or metatype.startswith("Literal")
        ):
            width = int(width / 2)

        part = Part(data=data, id=id_, width=width)
        part.title = Compartment().make_labels(
            headings=[
                f"«{metatype}»",
                f"{label}",
            ],
        )

        # TODO: add properties
        properties = []
        if properties:
            part.attrs = Compartment().make_labels(
                headings=["properties"],
                content=[
                    cls.make_property_label(prop)
                    for prop in properties
                ],
            )
        return part
