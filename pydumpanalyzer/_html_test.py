''' this contains tests for the _html.py file '''

import pytest

from _html import *
from abstract_database import AbstractDatabase, Column

def test_html_link_string():
    ''' ensures getHtmlLinkString works as expected '''
    URL = 'https://google.com'
    TXT = 'Google'
    assert getHtmlLinkString(URL, TXT) == r'<a href="%s">%s</a>' % (URL, TXT)

def test_drop_left_string():
    ''' ensures getDropLeft works as expected '''
    txt = getDropLeft('TITLE', [('TEXT', 'http://LINK'),])
    assert txt.count('TITLE') == 1
    assert txt.count('TEXT') == 1
    assert txt.count('http://LINK') == 1
    assert txt.count('"') % 2 == 0

def test_invalid_html_table_row():
    ''' ensures that a row with the incorrect number of columns raises properly '''
    table = HtmlTable(['A', 'B', 'C'])
    assert table.__html__()

    with pytest.raises(ValueError):
        table.addRow(['OnlyOne'])

    table.addRow(['One', 'Two', 'Three'])

def test_search_can_be_added():
    ''' ensures we can addSearch '''
    table = HtmlTable(['A', 'B', 'C'], addSearch=False)
    assert table.__html__()

    assert 'This is code for search' not in table.__html__()

    table = HtmlTable(['A', 'B', 'C'], addSearch=True)
    assert table.__html__()

    assert 'This is code for search' in table.__html__()

def test_class_can_be_set():
    ''' ensures we can set the classes on a table '''
    table = HtmlTable(['A', 'B', 'C'])
    assert table.__html__()

    assert 'class=\"\"' in table.__html__()

    CLASSNAME = 'the class'
    table = HtmlTable(['A', 'B', 'C'], classes=CLASSNAME)
    assert ('class=\"%s\"' % CLASSNAME) in table.__html__()

def test_can_set_name():
    ''' ensures we can set the name on a table '''
    table = HtmlTable(['A', 'B', 'C'], name="TheName")
    assert table.__html__()

    assert 'TheName</h2>' in table.__html__()

def test_id_is_unique():
    ''' ensures that the id is unique '''
    ids = [HtmlTable([]).id for i in range(100)]
    assert len(ids) == len(set(ids))

def test_from_cursor():
    ''' ensures we can create a table from a cursor '''
    with AbstractDatabase() as db:
        assert db.createTable('OurTable', [
            Column("Column1", 'TEXT')
        ])
        assert db.addRow('OurTable', {
            'Column1' : 'MyValue'
        })

        cursor = db.execute("SELECT * FROM OurTable")
        assert cursor
        t = HtmlTable.fromCursor(cursor)
        html = t.__html__()
        assert html.count('MyValue') == 1
        assert html.count('Column1') == 1

def test_modifying_all_rows():
    ''' ensures that the modify all rows function works '''
    h = HtmlTable(['A', 'B', 'C'])
    h.addRow(['0', '1', '2'])
    h.addRow(['3', '4', '5'])

    def perRowFunction(row):
        if row[0] == '0':
            row[0] = '10'
        return row

    h.modifyAllRows(perRowFunction)
    assert h.rows[0] == ['10', '1', '2']
    assert h.rows[1] == ['3', '4', '5']

def test_hiding_columns():
    ''' ensures we can hide columns '''
    h = HtmlTable(['A', 'B', 'C'])
    h.addRow(['0', '9999', '2'])
    h.addRow(['3', '4444', '5'])

    assert 'B' in h.__html__()
    assert '9999' in h.__html__()
    assert '4444' in h.__html__()
    assert len(h.tableHeaders) == 3

    h.removeColumns(['B'])

    assert 'B' not in h.__html__()
    assert '9999' not in h.__html__()
    assert '4444' not in h.__html__()
    assert len(h.tableHeaders) == 2

def test_cell_from_row():
    ''' ensures we can get the given cell from a row/columName '''
    h = HtmlTable(['A', 'B', 'C'])
    h.addRow(['0', '9999', '2'])
    h.addRow(['3', '4444', '5'])

    assert h.getCellFromRow(h.rows[0], 'C') == '2'
    assert h.getCellFromRow(h.rows[1], 'B') == '4444'

def test_add_column():
    ''' ensures we can get the given cell from a row/columName '''
    h = HtmlTable(['A', 'B', 'C'])
    h.addRow(['0', '9999', '2'])
    h.addRow(['3', '4444', '5'])

    h.addColumn('D')
    assert len(h.tableHeaders) == 4
    assert h.tableHeaders[-1] == 'D'
    for i in h.rows:
        assert len(i) == 4