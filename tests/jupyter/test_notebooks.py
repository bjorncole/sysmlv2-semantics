from testbook import testbook


@testbook("notebooks/Tutorial.ipynb", execute=True)
def test_tutorial(tb):
    """Test the Tutorial notebook"""
    client = tb.ref("client")
    diagram = tb.ref("diagram")

    assert len(diagram.model.elements) > 0

    assert len(diagram.model.elements) == len(client.model.elements)

    assert not set(diagram.model.elements).symmetric_difference(set(client.model.elements))


@testbook("dev_doc/Playbook Explorer Parts Test.ipynb", execute=True)
def test_simple_parts_explorer(tb):
    m0_interpretation = tb.ref("m0_interpretation")
    assert m0_interpretation


@testbook("dev_doc/SysML Model.ipynb", execute=True)
def test_sysml_model(tb):
    an_element = tb.ref("an_element")
    assert an_element._id == "78c8e7e1-1ac0-4a45-ac30-830ec479abb2"
