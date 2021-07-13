from copy import deepcopy

from tests.conftest import all_models, kerbal_model


def test_respect_of_sysml(all_models):
    for model in all_models.values():
        for element in model.elements.values():
            element_attrs = set(super(element.__class__, element).__dir__())
            derived_attrs = set(element._derived)
            sysml_attrs = set(element._data)
            common_attrs = tuple(sorted(element_attrs.intersection(sysml_attrs)))
            assert not common_attrs, f"Found Element attributes conflicting with SysML: {common_attrs}"
            common_attrs = tuple(sorted(derived_attrs.intersection(sysml_attrs)))
            assert not common_attrs, f"Found derived attributes conflicting with SysML: {common_attrs}"


def test_kerbal_model(kerbal_model):
    model = kerbal_model
    kerbal = model.ownedElement["Kerbal"]

    assert kerbal.name == "Kerbal", f"Element name should be 'Kerbal', not '{kerbal.name}'"
    assert kerbal == kerbal._id, f"Element should equate to its id"

    my_rocket = kerbal(name="My Rocket")
    assert my_rocket.name == "My Rocket", f"Instance should be called 'My Rocket', not '{my_rocket.name}'"

    assert kerbal.ownedElement["Parts Library"].ownedElement["FL-T200 Fuel Tank"].ownedElement["Empty Mass"].ownedElement[0].value == 0.125


def test_relationships(kerbal_model):
    model = kerbal_model

    for element in model.elements.values():
        if element.name == "Kerbal Rocket Part":
            rocket_part = element

    for subclass in rocket_part.reverseSuperclassing:
        if subclass.name == "Parachute":
            break

    assert subclass.throughSuperclassing[0].name == rocket_part.name


def test_accessors(kerbal_model):
    model = kerbal_model
    for element in model.elements.values():
        if element._metatype == "ReturnParameterMembership":
            a_return_parameter_membership = element
    assert isinstance(a_return_parameter_membership.relatedElement[0].value, int)

    assert a_return_parameter_membership.target[0].reverseReturnParameterMembership[0] == a_return_parameter_membership.relatedElement[0]

    value = a_return_parameter_membership.get("some_missing_key", "a default for something")
    assert value == "a default for something"

    assert a_return_parameter_membership.get("some_other_missing_key") is None

    source, target = a_return_parameter_membership.relatedElement
    assert source.throughReturnParameterMembership[0] == target
    assert target.reverseReturnParameterMembership[0] == source
