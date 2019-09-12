''' home to cross-functional utilities '''

import contextlib
import io
import os
import shutil
import tempfile
import uuid

from csmlog_setup import getLogger

logger = getLogger(__file__)

def getUniqueId():
    ''' gets a unique id string '''
    return str(uuid.uuid4())

def getUniqueTableName():
    ''' gets a psuedo random name for a table '''
    uid = getUniqueId()
    return 'table_' + uid.replace('-', '')

@contextlib.contextmanager
def temporaryFilePath(delete=True):
    ''' yields a path we can use for temp files... will attempt to delete it after use '''
    path = None
    while True:
        path = os.path.join(tempfile.gettempdir(), 'pda_' + getUniqueId())
        if not os.path.exists(path):
            break
    try:
        yield path
    finally:
        if delete:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)

def textToSafeHtmlText(s):
    ''' coerces a string into html-safe text '''
    return s.replace('\n', '<br>').replace(' ', '&nbsp;')

def zipDirectoryToBytesIo(directory):
    ''' zips a directory and returns a io.BytesIO object '''
    with temporaryFilePath() as tempPath:
        shutil.make_archive(tempPath, 'zip', directory)
        with open(tempPath + '.zip', 'rb') as f:
            fullBinaryBytesIo = io.BytesIO(f.read())
            fullBinaryBytesIo.seek(0)

        return fullBinaryBytesIo
