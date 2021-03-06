''' this file is home to the flask-based application that is the following:
    1. Receiver and storer of symbol files and executables
    2. Receiver and storer of crash dumps
    3. Analyzer of crash dumps
    4. Windows symbol server when accessible via an endpoint
'''
import datetime
import enum
import io
import itertools
import os
import pickle
import traceback

import flask
import flask_selfdoc
from werkzeug.exceptions import HTTPException

import __version__
import _html
import utility
from csmlog_setup import enableConsoleLogging, getLogger
from storage import Storage

CACHED_ANALYSIS_FILE_NAME = 'analysis.pickle'
THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_STORAGE_LOCATION = os.path.join(THIS_DIR, 'storage')
WINDOWS_SYMBOLS_LOCATION = os.path.join(ROOT_STORAGE_LOCATION, "WindowsSymbols")

app = flask.Flask("PyDumpAnalyzerFlaskApp")
auto = flask_selfdoc.Autodoc(app)
logger = getLogger(__file__)

class WEBPAGES_NAVBAR(enum.Enum):
    ''' enum with all top level web pages for the navbar '''
    API_Docs = '/show/apidocs/'

class WEBPAGES_NOT_NAVBAR(enum.Enum):
    ''' enum with all outward web pages. Ones that are in here,
    but not in WEBPAGES_NAVBAR are not shown in the navbar '''
    Add_Item = '/add'
    Home = '/'
    View_Application_Table = '/show/application_table/<applicationName>'
    Get_Analysis = '/get/analysis/<applicationName>/<rowUid>'
    Get_File = '/get/file/<applicationName>/<rowUid>/<column>'
    Get_Windows_Symbols = '/get/windows/symbols/<path:path>'

WEBPAGES = enum.Enum('WEBPAGES', [(i.name, i.value) for i in itertools.chain(WEBPAGES_NAVBAR, WEBPAGES_NOT_NAVBAR)])

@app.context_processor
def injectTemplateContext():
    ''' everything returned in this function is added to the context for all
    templates that flask renders. Only global, template driven things should be here. '''
    return {
        # this is the version of PDA...
        'pda_version' : __version__.__version__,
        'navItems' : [(a.name.replace('_', ' '), a.value) for a in list(WEBPAGES_NAVBAR)]
    }

@app.route(WEBPAGES.API_Docs.value, methods=['GET'])
def apiDocumentation():
    ''' returns a lovely documentation page of all supported APIs. Generated by flask_selfdoc. '''
    return flask.render_template('base.html', html_content=auto.html())

@app.route(WEBPAGES.Home.value, methods=['GET'])
def home():
    ''' the home page for the app '''
    with Storage() as storage:
        cursor = storage.database.execute("SELECT Name FROM Applications")
        table = _html.HtmlTable.fromCursor(cursor, classes='content', name="Applications")

        if not table:
            table = '<p>No applications have reported back to PDA... yet!</p>'
        else:
            table.modifyAllRows(lambda row: [_html.getHtmlLinkString(flask.url_for('viewApplicationTable', applicationName=row[0]), row[0])])

    return flask.render_template('home.html', html_content=table)

@app.route(WEBPAGES.View_Application_Table.value, methods=['GET'])
def viewApplicationTable(applicationName):
    ''' used to give back a view of the given database table '''
    with Storage() as storage:
        table = storage.getApplicationTable(applicationName)
        return flask.render_template('table_view.html', table_content=table, title=applicationName)

@app.route(WEBPAGES.Get_File.value, methods=['GET'])
def getFile(applicationName, rowUid, column):
    ''' this handler is not documented for external use.
    From applicationName, rowUid, column (name) we can get the blob assoicated '''
    with Storage() as s:
        blob = s.getApplicationCell(applicationName, rowUid, column)
        if not blob:
            flask.abort(404)

        # if we can get the 'real name', use it
        fileName = column
        if column in ('SymbolsFile', 'ExecutableFile', 'CrashDumpFile'):
            fileName = s.getApplicationCell(applicationName, rowUid, column + "Name")

    if isinstance(blob, str):
        blob = blob.encode()

    return flask.send_file(io.BytesIO(blob), as_attachment=True, attachment_filename=fileName, mimetype='application/x-binary')

@app.route(WEBPAGES.Get_Analysis.value, methods=['GET'])
def getAnalysis(applicationName, rowUid):
    ''' will get back an analysis page based off the given application name and uid.
    Optionally the useCache param may be used. By default it is True. If False is given, cache will be
    removed, then analysis regenerated for the given uid's crash dump '''
    useCache = True if flask.request.args.get('useCache', default="True", type=str) == "True" else False
    with Storage() as storage:
        analysis = storage.getAnalysis(applicationName, rowUid, useCache)
        return flask.render_template('analysis.html', analysis=utility.textToSafeHtmlText(str(analysis)), title="Analysis", uuid=rowUid, application=applicationName)

@app.errorhandler(Exception)
def error_handler(e):
    ''' this will handle all http errors we may encounter with a custom template '''
    logger.error("Giving back an error: %s\n... that error was encountered serving: %s" % (str(e), flask.request.path))

    # if an assertion gets here, it means something has gone very wrong.
    if not hasattr(e, 'code'):
        try:
            txt = "Unknown Error made it to the error handler: " + traceback.format_exc()
        except:
            txt = "Unknown Error"

        logger.error(txt)
        return flask.render_template('error.html', code=400, errString=utility.textToSafeHtmlText(txt)), 400

    return flask.render_template('error.html', code=e.code, errString=str(e)), e.code

@app.route(WEBPAGES.Add_Item.value, methods=['POST'])
@auto.doc()
def addHandler():
    ''' this handler is called when an item is being added via a POST request. A single call to this API shall not have unrelated Symbols/Executable/CrashDump files.
        In other words, do not give an Execuable that isn't related to the given Symbols file. Do seperate API calls for unrelated files.

    Required form-data Body Fields:
    OperatingSystem: String: (Should be "Windows")
    Application:     String: The name of the application this addition is related to

    At least one of the following is also required:
    SymbolsFile:     File: Symbols file for the application (On Windows a .pdb file can be given)
    ExecutableFile:  File: The executable to be debugged later (Can be a .exe, .dll, etc.)
    CrashDumpFile:   File: The dump file to be analyzed. (On Windows, the crash dump can be sent at a different time from the ExecutableFile and SymbolsFile)

    Optional form-data Body Fields:
    ApplicationVersion: String: Version for the application
    Tag:                String: Arbitrary tag for this upload. (Can be used for later filtering)
    '''
    with Storage() as storage:
        return storage.addFromAddRequest(flask.request)

@app.route(WEBPAGES.Get_Windows_Symbols.value, methods=['GET'])
@auto.doc()
def getWindowsSymbols(path):
    ''' This endpoint can be used as a Windows Symbol server for all Windows executables and symbols files.
    For information on Symbol Stores/Servers from Microsoft, check: https://docs.microsoft.com/en-us/windows/win32/debug/using-symsrv'''
    with Storage() as storage:
        return flask.send_file(storage.getWindowsSymbolFilePath(path))

if __name__ == '__main__':
    app.url_map.strict_slashes = False
    enableConsoleLogging()
    app.run()