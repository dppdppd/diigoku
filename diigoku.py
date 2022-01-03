# -*- coding: utf-8 -*-

import sys
import logging
import buku
from buku import BukuDb, parse_tags, prompt
import requests
from requests.auth import HTTPBasicAuth
from dateutil import parser
import argparse
import itertools

argParser = argparse.ArgumentParser( description = 'Import Diigo bookmarks into Buku')
argParser.add_argument('key', metavar='key', type=str, help='Your Diigo application key')
argParser.add_argument('username', metavar='username', type=str, help='Your Diigo username')


spinner = itertools.cycle(['-', '\\', '|', '/'])

key = argParser.parse_args().key
user = argParser.parse_args().username

# debugging variables
limit = -1
count = -1

logging.basicConfig(filename='diigoku.log', encoding='utf-8', level=logging.INFO, filemode='w')

def buku_item_to_dict(b_item):
    """ convert buku item to universal dict """
    out = {
        'url': b_item[1],
        'title': b_item[2],
        'tags': sorted(b_item[3].split(',')[1:-1]),
        'timestamp': b_item[0],
        'desc' : b_item[4]
    }

    return out


def tags_to_tagstring(tag_list):
    """ convert list of tags to tagstring """
    if tag_list == []:
        return ','

    return ',{},'.format(','.join(tag_list))

def no_tag(var):
    return var != 'no_tag'


def diigo_get_desc( item ):
    desc = f"description:\n{item.get( 'desc' )}\n" if item.get('desc') else ""
    return desc

def diigo_get_comm( item ):
    rval = ""
    if item.get( 'comments' ):
        rval+= "comments:\n"
        for c in item.get( 'comments' ):
            rval += "comment\n"
            rval += f"{c.get('content')} --{c.get('user')}, {c.get('created_at')}\n"
    return rval

def diigo_get_annot( item ):
    rval = ""
    if item.get( 'annotations' ):
        rval += '\nannotations:\n'
        for a in item.get( 'annotations' ):
            rval += "quote\n"
            rval += f"{a.get('content')}\n"
            rval += diigo_get_comm( a )
    return rval

def diigo_make_desc( item ):
    desc = diigo_get_desc( item )
    anno = diigo_get_annot( item )
    comm = diigo_get_comm( item )
    rval = f"{desc}{anno}{comm}"
    return rval

def diigo_item_to_dict(p_item):
    """ convert diigo item to universal dict """
    out = {
        'url': p_item.get('url'),
        'title': p_item.get('title'),
        'tags': sorted((filter(no_tag, p_item.get('tags').split(',')))),
        'timestamp': parser.parse(p_item.get('created_at')),
        'desc' : diigo_make_desc( p_item )
    }
    return out

def sort_dict_items(item_list):
    """ sort list of dict items based on update time """
    return sorted(item_list, key=lambda x: x['timestamp'])


def dict_list_difference(l1, l2):
    """ return items in l1 but not in l2 """
    return [i for i in l1 if i['url'] not in [j['url'] for j in l2]]


def dict_list_ensure_unique(item_list):
    """ ensure all items in list have a unique url (newer wins) """
    return list({i['url']: i for i in item_list}.values())

start = 0

def get_bookmarks( start, count ):
    if limit >= 0 and start >= limit:
        return ''

    if count == -1 or count > 100:
        count = 100

    url = f'https://secure.diigo.com/api/v2/bookmarks?key={key}&user={user}&filter=all&count={count}&start={start}'
    response = requests.get(url, auth=HTTPBasicAuth('idomagal','2diigo888'))

    sys.stdout.write(next(spinner))   # write the next character
    sys.stdout.flush()                # flush stdout buffer (actual character display)
    sys.stdout.write('\b')            # erase the last written char

    response.close()
    return response.json()

#--------------------------------------------------------------------------------------------------------
#
bukudb = buku.BukuDb()
buku_items = [buku_item_to_dict(i) for i in bukudb.get_rec_all()]
logging.info(f'{len(buku_items)} buku items retrieved')
buku_items = sort_dict_items(buku_items)

sys.stdout.write( "Fetching bookmarks..." )

diigo_bookmarks = []
while bookmarks := get_bookmarks(start=start, count=count):
    if bookmarks:
        for b in bookmarks:
            logging.info( f'Recieving -- {b.get("url")}' )
        diigo_bookmarks += bookmarks
        start += 100


sys.stdout.write( "done!\n" )

sys.stdout.write( f'{len(diigo_bookmarks)} bookmarks fetched.\n' )

# diigo delivers bookmarks in reverse chrono order. We need to flip it
diigo_bookmarks.reverse()

# convert them to a generic object
diigoitems = [diigo_item_to_dict(i)
              for i in diigo_bookmarks]

# dedupe
diigoitems = dict_list_ensure_unique(diigoitems)

# sort the results
diigoitems = sort_dict_items(diigoitems)

# Add items to buku
new_buku_items = dict_list_difference(diigoitems, buku_items)
print(f'Adding {len(new_buku_items)} new items to buku')
for item in new_buku_items:
    bukudb.add_rec(
        item['url'],
        title_in = item['title'],
        tags_in = tags_to_tagstring(item['tags']),
        desc = item['desc'],
        delay_commit = True,
        fetch = False,
        immutable = True
    )
bukudb.conn.commit()
