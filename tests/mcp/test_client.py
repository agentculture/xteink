import pytest

from xteink import client as c


def make(api_url, key):
    return c.Client(api_url, key)


def test_upload_list_get_delete(api_url, api_key):
    cl = make(api_url, api_key)
    res = cl.upload(b"hello text", "note.txt", title="Note", author="Me")
    assert res["created"] is True
    item = res["item"]
    assert cl.get_item(item["id"])["title"] == "Note"
    assert [i["id"] for i in cl.list_library(q="Note")] == [item["id"]]
    assert cl.upload(b"hello text", "note.txt", title="Note")["created"] is False
    cl.delete_item(item["id"])
    with pytest.raises(c.ApiError) as e:
        cl.get_item(item["id"])
    assert e.value.status == 404


def test_upload_markdown_is_article(api_url, api_key):
    item = make(api_url, api_key).upload(b"# Hi\n\nbody", "a.md", title="A")["item"]
    assert item["kind"] == "article"


def test_upload_path(api_url, api_key, tmp_path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"from disk")
    res = make(api_url, api_key).upload(path=f, title="Disk")
    assert res["item"]["title"] == "Disk"


def test_upload_arg_validation(api_url, api_key):
    cl = make(api_url, api_key)
    with pytest.raises(ValueError):
        cl.upload()
    with pytest.raises(ValueError):
        cl.upload(b"x")  # no filename


def test_unsupported_format_error_code(api_url, api_key):
    client = make(api_url, api_key)
    with pytest.raises(c.ApiError) as e:
        client.upload(b"x", "a.xyz")
    assert e.value.status == 415
    assert e.value.code
    assert e.value.detail


def test_devices_and_queue(api_url, api_key, device):
    cl = make(api_url, api_key)
    item = cl.upload(b"t", "t.txt", title="T")["item"]
    assert [d["name"] for d in cl.list_devices()] == ["reader"]
    cl.queue_item(device.id, item["id"])
    assert [e["item_id"] for e in cl.device_queue(device.id)] == [item["id"]]


def test_bad_key_is_authentication_error_without_leaking(api_url):
    secret = "xtk_" + "x" * 8 + "_" + "fake"
    cl = make(api_url, secret)
    with pytest.raises(c.AuthenticationError) as e:
        cl.list_library()
    assert e.value.status == 401
    assert secret not in str(e.value)
    assert secret not in repr(e.value)
    assert secret not in repr(cl)


def test_unreachable():
    client = c.Client("http://127.0.0.1:1", "k", timeout=2)
    with pytest.raises(c.ServerUnreachable) as e:
        client.list_library()
    assert e.value.code == "server_unreachable"


def test_url_scheme_restricted():
    with pytest.raises(c.ConfigError):
        c.Client("file:///etc/passwd", "k")


def test_from_env():
    with pytest.raises(c.ConfigError):
        c.from_env({})
    cl = c.from_env({"XTEINK_API_KEY": "k"})
    assert cl.base_url == "http://127.0.0.1:8780"
    assert c.from_env({"XTEINK_API_KEY": "k", "XTEINK_URL": "http://h:1/"}).base_url == "http://h:1"


def test_register_and_revoke_device(api_url, api_key):
    cl = make(api_url, api_key)
    minted = cl.register_device("pocket", mirror=True)
    assert minted["key"].startswith("xtd_")
    assert minted["device"]["mirror"] is True
    cl.revoke_device(minted["device"]["id"])
    assert any(d["id"] == minted["device"]["id"] and d["revoked_at"] for d in cl.list_devices())
