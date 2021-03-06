''' this is the home for various html helpers '''

from utility import getUniqueId
from csmlog_setup import getLogger

logger = getLogger(__file__)

def getHtmlLinkString(url, text):
    ''' given a url/text returns an a '''
    return r'<a href="%s">%s</a>' % (url, text)

def getDropLeft(title, textCommaLinks):
    ''' returns text for a bootstrap 4 dropleft '''
    return r'''
    <div class="dropleft">
        <button class="btn btn-secondary dropdown-toggle" type="button" id="dropdownMenuButton" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
            %s
        </button>
        <div class="dropdown-menu" aria-labelledby="dropdownMenuButton">
            %s
        </div>
    </div>
    ''' % (title, ('\n'.join([('<a class="dropdown-item" href="%s">%s</a>' % (val[1], val[0])) for val in textCommaLinks])))

SEARCH_CODE = '''
<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.4.1/jquery.min.js"></script>
<script>
// This is code for search
$(document).ready(function(){{
  $("#input_{id}").on("keyup", function() {{
    var value = $(this).val().toLowerCase();
    $("#table_{id} tr").filter(function() {{
      $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1)
    }});
  }});
}});
</script>

<input id="input_{id}" type="text" placeholder="Search..." class="{classes}">
'''

TABLE_CONTENT = '''
<table style="width:100%;" class="{classes}">
    <thead style="text-align: left">
        {headers}
    </thead>
    <tbody id="table_{id}">
        {rows}
    </tbody>
</table
'''

FULL_CONTENT = '''
<h2 class="{classes}">{name}</h2>
<div class="{classes}" style="border: 1px solid black;">
{searchCode}
{tableContent}
</div>
'''

class HtmlTable(object):
    ''' this object is used to create an HTML table, with optional search functionality '''
    def __init__(self, tableHeaders, name=None, addSearch=True, classes=None):
        ''' initializer for html table object '''
        self.tableHeaders = tableHeaders
        self.name = name if name is not None else ''
        self.addSearch = addSearch
        self.classes = classes if classes is not None else ''
        self.id = getUniqueId()
        self.rows = []

    @classmethod
    def fromCursor(cls, cursor, name=None, addSearch=True, classes=None):
        ''' helper to get an HtmlTable from a database cursor '''
        if not cursor:
            logger.error("Cursor appears to be invalid")
            return False

        results = cursor.fetchall()
        if not results:
            logger.warning("Empty results from valid cursor")

        tableHeaders = [a[0] for a in cursor.description]
        retTable = HtmlTable(tableHeaders=tableHeaders, name=name, addSearch=addSearch, classes=classes)
        for result in results:
            retTable.addRow(list(result))

        return retTable

    def addRow(self, row):
        ''' adds a row to the table. This row must have the same number of items as the
        original tableHeaders had. '''
        if len(row) != len(self.tableHeaders):
            raise ValueError("number of items in a row (%d) must match number of items in tableHeaders (%d)" % (len(row), len(self.tableHeaders)))

        self.rows.append(row)

    def modifyAllRows(self, func):
        ''' will go through all rows and call the given function on each row.
        The function should return the modified version of the row to replace in the table'''
        for idx, row in enumerate(self.rows):
            self.rows[idx] = func(row)

    def removeColumns(self, columnNames):
        ''' hides the given columns (by header name) from the table (by removing respective cells) '''
        if not isinstance(columnNames, (list, tuple)):
            columnNames = [columnNames]

        indexes = sorted([self.tableHeaders.index(c) for c in columnNames], reverse=True)

        def deleter(row):
            ''' deletes calculated indexes from the given row '''
            for idx in indexes:
                del row[idx]
            return row

        deleter(self.tableHeaders)
        self.modifyAllRows(deleter)

    def getCellFromRow(self, row, columnName):
        ''' gets a given cell from a row and the desired columnName '''
        idx = self.tableHeaders.index(columnName)
        return row[idx]

    def addColumn(self, headerName):
        ''' add a column to the table (with a given name) '''
        self.tableHeaders.append(headerName)
        self.modifyAllRows(lambda row: row + [None])

    def __html__(self):
        ''' general purpose to-html method for this table '''
        searchCode = ''
        if self.addSearch:
            searchCode += SEARCH_CODE.format(id=self.id, classes=self.classes)

        headerText = '<tr>\n'
        for row in self.tableHeaders:
            headerText += '<th>%s</th>\n' % (row)
        headerText += '</tr>\n'

        if self.rows:
            rowText = ''
            for row in reversed(self.rows):
                rowText += '<tr>\n'
                for colIdx, value in enumerate(row):
                    rowText += '<td>%s</td>\n' % (value)
                rowText += '</tr>\n'
        else:
            rowText = '... Table is empty (no rows)'

        tableContent = TABLE_CONTENT.format(id=self.id, rows=rowText, headers=headerText, classes=self.classes)

        retStr = FULL_CONTENT.format(classes=self.classes, searchCode=searchCode, tableContent=tableContent, name=self.name)
        return retStr


