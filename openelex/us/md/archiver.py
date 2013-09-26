import os
import json
from openelex.base.archiver import BaseArchiver
import boto
from boto.s3.key import Key

"""
Usage:

>>> from openelex.us.md import archiver
>>> a = archiver.ResultsArchiver()
>>> a.run(2012)
"""


class ResultsArchiver(BaseArchiver):
    
    def run(self, year):
        filenames = self.filename_mappings()[str(year)]
        bucket = self.conn.get_bucket('openelex-data')
        path = "us/states/md/raw/"
        for file in filenames:
            k = Key(bucket)
            k.key = os.path.join(path, file['generated_name'])
            k.set_contents_from_filename(os.path.join(self.cache_dir, file['generated_name']))
        
    def filename_mappings(self):
        filename = os.path.join(self.mappings_dir, 'filenames.json')
        with open(filename) as f:
            try:
                mappings = json.loads(f.read())
            except:
                mappings = {}
            return mappings