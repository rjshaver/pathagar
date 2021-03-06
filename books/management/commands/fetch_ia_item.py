#!/usr/bin/env python
# Initial standalone script by rajbot
# Ported to django management by Aneesh Dogra (aneesh@activitycentral.com)

"""
This script will download all of an user's bookmarked items from archive.org.
"""

from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
from django.conf import settings

import re
import os
import sys
import json
import time
import urllib
import subprocess


# Customize this script by editing global variables below
# uncomment formats below to download more data
# formats are listed in order of preference, i.e. prefer 'Text' over 'DjVuTXT'
requested_formats = {'pdf':  ['Text PDF', 'Additional Text PDF', 'Image Container PDF'],
                     'epub': ['EPUB'],
                     'meta': ['Metadata'],
                     'text': ['Text', 'DjVuTXT'],
                     'jpeg': ['JPEG'],
                     #'djvu': ['DjVu'],
                    }

download_directory = os.path.join(settings.MEDIA_ROOT, "books")

should_download_cover = True

def load_user_bookmarks(user):
    """Return an array of bookmarked items for a given user.
    An example of user bookmarks: http://archive.org/bookmarks/sverma"""

    print user
    url = 'http://archive.org/bookmarks/%s?output=json' % user
    f = urllib.urlopen(url)
    return json.load(f)

def get_item_meatadata(item_id):
    """Returns an object from the archive.org Metadata API"""

    url = 'http://archive.org/metadata/%s' % item_id
    f = urllib.urlopen(url)
    return json.load(f)

def get_download_url(item_id, file):

    prefix = 'http://archive.org/download/'
    return prefix + os.path.join(item_id, file)

def download_files(item_id, matching_files, item_dir):

    for file in matching_files:
        download_path = os.path.join(item_dir, file)

        if os.path.exists(download_path):
            print "    Already downloaded", file
            continue

        parent_dir = os.path.dirname(download_path)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir)

        print "    Downloading", file, "to", download_path
        download_url= get_download_url(item_id, file)
        ret = subprocess.call(['wget', download_url, '-O', download_path,
                               '--limit-rate=1000k', '--user-agent=fetch_ia_item.py', '-q'])

        if 0 != ret:
            print "    ERROR DOWNLOADING", download_path
            sys.exit(-1)

        time.sleep(0.5)

def download_item(item_id, mediatype, metadata, out_dir, formats):
    """Download an archive.org item into the specified directory"""

    print "Downloading", item_id

    item_dir = os.path.join(out_dir, item_id)

    if not os.path.exists(item_dir):
        os.mkdir(item_dir)

    files_list = metadata['files']

    if 'gutenberg' == metadata['metadata']['collection']:
        #For Project Gutenberg books, download entire directory
        matching_files = [x['name'] for x in files_list]
        download_files(item_id, matching_files, item_dir)
        return

    for key, format_list in formats.iteritems():
        for format in format_list:
            matching_files = [x['name'] for x in files_list if x['format']==format]
            download_files(item_id, matching_files, item_dir)

            #if we found some matching files in for this format, move on to next format
            #(i.e. if we downloaded a Text, no need to download DjVuTXT as well)
            if len(matching_files) > 0:
                break

def download_cover(item_id, metadata, download_directory):
    files_list = metadata['files']

    item_dir = os.path.join(download_directory, item_id)
    cover_formats = set(['JPEG Thumb', 'JPEG', 'Animated GIF'])

    covers = [x['name'] for x in files_list if x['format'] in cover_formats]

    if covers:
        download_files(item_id, [covers[0]], item_dir)
        return covers[0]

    #no JPEG Thumbs, JPEGs, or AGIFs, return None
    return None

def add_to_pathagar(pathagar_books, mdata, cover_image):
    pathagar_formats = []
    if 'epub' in requested_formats:
        pathagar_formats += requested_formats['epub']

    if 'pdf' in requested_formats:
        pathagar_formats += requested_formats['pdf']

    if not pathagar_formats:
        return

    metadata = mdata['metadata']
    files_list = mdata['files']
    book_paths = [x['name'] for x in files_list if x['format'] in pathagar_formats]

    if not book_paths:
        return

    item_dir = os.path.join(download_directory, metadata['identifier'])
    book_path = os.path.abspath(os.path.join(item_dir, book_paths[0]))
    # Some fields are not required
    if 'description' in metadata:
        summary = metadata['description']
    else:
        summary = metadata['title']

    if 'creator' in metadata:
        author = metadata['creator']
    else:
        author = ''

    book = {
        "book_path": os.path.abspath(book_path),
        "a_title": metadata['title'],
        "a_author": author,
        "a_status": "Published",
        "a_summary": summary,
    }

    if cover_image:
        book['cover_path'] = os.path.abspath(os.path.join(item_dir, cover_image))


    if 'subject' in metadata:
        if isinstance(metadata['subject'], list):
            tags = metadata['subject']
        else:
            tags = re.split(';\s*', metadata['subject'])

        book['tags'] = tags

    pathagar_books.append(book)


class Command(BaseCommand):
    help = "A script to download all of an user's bookmarked items from archive.org"
    args = "<--username ... --out ...>"
    
    option_list = BaseCommand.option_list + (
        make_option('--username',
            dest='username',
            default=False,
            help='The username at archive.org'),
        make_option('--out',
            dest='out_json_path',
            default=False,
            help='The json file to write the output to'),        
        )
    def handle(self, *args, **options):
        if not options['username']:
           raise CommandError("Option '--username ...' must be specified.")

        if not os.path.exists(download_directory):
            os.mkdir(download_directory, 0o755)

        bookmarks = load_user_bookmarks(options['username'])
        pathagar_books = []
        for item in bookmarks:
            item_id = item['identifier']
            metadata = get_item_meatadata(item_id)

            download_item(item_id, item['mediatype'], metadata, download_directory, requested_formats)

            if should_download_cover:
                cover_image = download_cover(item_id, metadata, download_directory)
            else:
                cover_image = None

            add_to_pathagar(pathagar_books, metadata, cover_image)

        if pathagar_books:
            if options['out_json_path']:
                fh = open(options['out_json_path'], 'w')
                json.dump(pathagar_books, fh, indent=4)
            else:
                print json.dumps(pathagar_books, indent = 4)
