
import pytest
import py
from devpi_server.filestore import *

pytestmark = [pytest.mark.writetransaction]

BytesIO = py.io.BytesIO

class TestFileStore:
    def test_maplink_deterministic(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.2.zip")
        entry1 = filestore.maplink(link)
        entry2 = filestore.maplink(link)
        assert entry1.relpath == entry2.relpath
        assert entry1.basename == "pytest-1.2.zip"
        assert py.builtin._istext(entry1.md5)

    def test_maplink_splitmd5_issue78(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.2.zip")
        entry1 = filestore.maplink(link)
        # check md5 directory structure (issue78)
        parts = entry1.relpath.split("/")
        parent2 = parts[-2]
        parent1 = parts[-3]
        assert parent1 == link.md5[:3]
        assert parent2 == link.md5[3:]

    def test_maplink(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.2.zip")
        entry1 = filestore.maplink(link)
        entry2 = filestore.maplink(link)
        assert not entry1.file_exists() and not entry2.file_exists()
        assert entry1 == entry2
        assert entry1.relpath.endswith("/pytest-1.2.zip")
        assert entry1.md5 == link.md5

    def test_maplink_replaced_release_not_cached_yet(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.2.zip")
        entry1 = filestore.maplink(link)
        assert not entry1.file_exists()
        assert entry1.md5 == link.md5
        newlink = gen.pypi_package_link("pytest-1.2.zip")
        entry2 = filestore.maplink(newlink)
        assert entry2.md5 == newlink.md5

    def test_maplink_replaced_release_already_cached(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.2.zip")
        entry1 = filestore.maplink(link)
        # pseudo-write a release file
        entry1.set_file_content(b"content")
        assert entry1.file_exists()
        newlink = gen.pypi_package_link("pytest-1.2.zip")
        entry2 = filestore.maplink(newlink)
        assert entry2.md5 == newlink.md5
        assert not entry2.file_exists()

    def test_file_delete(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.2.zip", md5=False)
        entry1 = filestore.maplink(link)
        entry1.set_file_content(b"")
        assert entry1.file_exists()
        entry1.file_delete()
        assert not entry1.file_exists()

    def test_maplink_egg(self, filestore, gen):
        link = gen.pypi_package_link("master#egg=pytest-dev", md5=False)
        entry1 = filestore.maplink(link)
        entry2 = filestore.maplink(link)
        assert entry1 == entry2
        assert entry1.relpath.endswith("/master")
        assert entry1.eggfragment == "pytest-dev"
        assert not entry1.md5
        assert entry1.url == link.url_nofrag
        assert entry1.eggfragment == "pytest-dev"

    def test_relpathentry(self, filestore, gen):
        link = gen.pypi_package_link("pytest-1.7.zip", md5=False)
        entry = filestore.maplink(link)
        assert entry.url == link.url
        assert not entry.file_exists()
        entry.set(md5="1" * 16)
        assert not entry.file_exists()
        entry.set_file_content(b"")
        assert entry.file_exists()
        assert entry.url == link.url
        assert entry.md5 == u"1" * 16

        # reget
        entry = FileEntry(entry.key)
        assert entry.file_exists()
        assert entry.url == link.url
        assert entry.md5 == u"1" * 16
        entry.delete()
        assert not entry.file_exists()

    def test_getfile(self, filestore, httpget, gen):
        link = gen.pypi_package_link("pytest-1.8.zip", md5=False)
        entry = filestore.maplink(link)
        assert not entry.md5 and not entry.file_exists()
        filestore.keyfs.restart_as_write_transaction()
        headers={"content-length": "3",
                 "last-modified": "Thu, 25 Nov 2010 20:00:27 GMT",
                 "content-type": "application/zip"}
        httpget.url2response[link.url] = dict(status_code=200,
                headers=headers, raw = BytesIO(b"123"))
        rheaders, bytes = filestore.getfile(entry.relpath,
                                            httpget, chunksize=1)
        assert rheaders["content-length"] == "3"
        assert rheaders["content-type"] == "application/zip"
        assert rheaders["last-modified"] == headers["last-modified"]
        assert bytes == b"123"

        # reget entry and check about content
        filestore.keyfs.restart_as_write_transaction()
        entry = filestore.get_file_entry(entry.relpath)
        assert entry.file_exists()
        assert entry.md5 == hashlib.md5(bytes).hexdigest()
        assert entry.size == 3
        rheaders, bytes = filestore.getfile(entry.relpath, None, chunksize=1)
        assert rheaders == headers
        assert bytes == b"123"

    def test_iterfile_remote_no_headers(self, filestore, httpget, gen):
        link = gen.pypi_package_link("pytest-1.8.zip", md5=False)
        entry = filestore.maplink(link)
        assert not entry.md5
        filestore.keyfs.restart_as_write_transaction()
        headers={}
        httpget.url2response[link.url] = dict(status_code=200,
                headers=headers, raw = BytesIO(b"123"))
        rheaders, bytes = filestore.getfile(entry.relpath,
                                            httpget, chunksize=1)
        assert rheaders["content-length"] == "3"
        assert rheaders.get("content-type") is None
        assert bytes == b"123"

    def test_iterfile_remote_error_size_mismatch(self, filestore, httpget, gen):
        link = gen.pypi_package_link("pytest-3.0.zip", md5=False)
        entry = filestore.maplink(link)
        assert not entry.md5
        filestore.keyfs.restart_as_write_transaction()
        headers={"content-length": "3",
                 "last-modified": "Thu, 25 Nov 2010 20:00:27 GMT",
                 "content-type": "application/zip"}
        httpget.url2response[link.url] = dict(status_code=200,
                headers=headers, raw = BytesIO(b"1"))
        with pytest.raises(ValueError):
            filestore.getfile(entry.relpath, httpget)

    def test_iterfile_remote_nosize(self, filestore, httpget, gen):
        link = gen.pypi_package_link("pytest-3.0.zip", md5=False)
        entry = filestore.maplink(link)
        assert not entry.md5
        filestore.keyfs.restart_as_write_transaction()
        headers={"last-modified": "Thu, 25 Nov 2010 20:00:27 GMT",
                 "content-length": None,
                 "content-type": "application/zip"}
        entry.sethttpheaders(headers)
        assert entry.size is None
        httpget.url2response[link.url] = dict(status_code=200,
                headers=headers, raw=BytesIO(b"1"))
        rheaders, received = filestore.getfile(entry.relpath,
                                               httpget, chunksize=3)
        assert received == b"1"
        entry2 = filestore.get_file_entry(entry.relpath)
        assert entry2.size == 1

    def test_iterfile_remote_error_md5(self, filestore, httpget, gen):
        link = gen.pypi_package_link("pytest-3.0.zip")
        entry = filestore.maplink(link)
        assert entry.md5 == link.md5
        filestore.keyfs.restart_as_write_transaction()
        headers={"content-length": "3",
                 "last-modified": "Thu, 25 Nov 2010 20:00:27 GMT",
                 "content-type": "application/zip"}
        httpget.url2response[link.url_nofrag] = dict(status_code=200,
                headers=headers, raw=BytesIO(b"123"))
        with pytest.raises(ValueError) as excinfo:
            filestore.getfile(entry.relpath, httpget)
        assert link.md5 in str(excinfo.value)
        assert not entry.file_exists()

    @pytest.mark.xfail(reason="disambiguation of downloads from urls"
            " whose content changes over time")
    def test_iterfile_eggfragment(self, filestore, httpget, gen):
        link = gen.pypi_package_link("master#egg=pytest-dev", md5=False)
        entry = filestore.maplink(link)
        assert entry.eggfragment
        assert entry.url
        headers={"content-length": "4",
                 "last-modified": "Thu, 25 Nov 2010 20:00:27 GMT",
                 "content-type": "application/zip"}

        httpget.mockresponse(entry.url, headers=headers, raw=BytesIO(b"1234"))
        rheaders, riter = filestore.iterfile(entry.relpath, httpget,
                                             chunksize=10)
        assert py.builtin.bytes().join(riter) == b"1234"
        httpget.mockresponse(entry.url, headers=headers, raw=BytesIO(b"3333"))
        rheaders, riter = filestore.iterfile(entry.relpath, httpget,
                                             chunksize=10)
        assert b"".join(riter) == b"3333"
        # XXX we could allow getting an old version if it exists
        # and a new request errors out
        #httpget.url2response[entry.url] = dict(status_code=500)
        #rheaders, riter = store.iterfile(entry.relpath, httpget, chunksize=10)
        #assert py.builtin.bytes().join(riter) == py.builtin.bytes("1234")

    def test_store_and_iter(self, filestore):
        content = b"hello"
        entry = filestore.store("user", "index", "something-1.0.zip", content)
        assert entry.md5 == hashlib.md5(content).hexdigest()
        assert entry.file_exists()
        filestore.keyfs.restart_as_write_transaction()
        entry2 = filestore.get_file_entry(entry.relpath)
        assert entry2.basename == "something-1.0.zip"
        assert entry2.file_exists()
        assert entry2.md5 == entry.md5
        assert entry2.last_modified
        headers, c = filestore.getfile(entry.relpath, httpget=None)
        assert c == content

    def test_add_testresult(self, filestore):
        #
        #link = URL("http://pypi.python.org/pkg/pytest-1.7.zip#md5=123")
        #entry = filestore.maplink(link)

        from test_devpi_server.example import tox_result_data
        md5 = tox_result_data["installpkg"]["md5"]
        data = json.dumps(tox_result_data)
        num = filestore.add_attachment(md5, "toxresult", data)
        res = filestore.get_attachment(md5, "toxresult", num)
        assert res == data
