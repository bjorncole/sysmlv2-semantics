import pytest

import requests
import urllib3

from tests.conftest import (
    all_kerbal_names,
    kerbal_client,
    kerbal_ids_by_type,
)


SYSML_SERVER_URL = "http://sysml2.intercax.com"


def bad_connection(host: str):
    try:
        requests.get(host)
        return False
    except:
        return True


def test_client_load_kerbal(kerbal_client):
    assert len(kerbal_client.model.elements) == 389


def test_client_load_find_names(all_kerbal_names):
    assert "Liquid Stage" in all_kerbal_names
    assert "$result" in all_kerbal_names
    assert "Empty Mass" in all_kerbal_names


def test_client_load_find_types(kerbal_ids_by_type):
    assert "PartDefinition" in kerbal_ids_by_type
    assert "FeatureTyping" in kerbal_ids_by_type
    assert "FeatureReferenceExpression" in kerbal_ids_by_type

    assert len(kerbal_ids_by_type["PartDefinition"]) == 17


def test_bad_connection(kerbal_client):
    with pytest.raises(urllib3.exceptions.MaxRetryError) as exc:
        kerbal_client.host_url = "http://some.bad.url"
    assert "Max retries exceeded" in exc.value.args[0]


@pytest.mark.skipif(
    bad_connection(host=SYSML_SERVER_URL),
    reason=f"Can't connect to {SYSML_SERVER_URL}",
)
def test_remote_connection(kerbal_client):
    kerbal_client.host_url = SYSML_SERVER_URL

    assert kerbal_client.projects
