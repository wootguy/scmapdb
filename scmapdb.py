# Python 3 required

# There's a bug somewhere that causes file handles to build up, so you might need to 
# set "ulimit -n" to something high like 4096 (1024 isn't enough), make sure to do it for root too if using crontab

# TODO / Feature requests:
# scmapdb repack file recovered but it overwrites default content (decay I think, point_checkpoint.as)
# scmapdb add "unreleased" category



from lxml import html
from lxml import etree
from datetime import datetime
from glob import glob
from pathlib import Path
import urllib.request, requests, mimetypes
import shutil, os.path, subprocess, stat, sys, time, filecmp, platform, io, contextlib, traceback
import patoolib, codecs, json, collections, hashlib, zlib, re, string
import socket
from requests.packages.urllib3.exceptions import InsecureRequestWarning

use_cache = True
force_zip_cache = False # always use zip cache, even if it's out of date
debug_zip = False
debug_repack = False # Don't delete the "repack" folder
unpack_nested = False # unpack nested archives
include_extras = False # move extras to a special subfolder instead of deleting them
verbose = True
log_to_file = True
include_readmes = True # include mapname_readme.txt files in the repack

domain_name = 'http://scmapdb.com'

# maps that won't be included in The Big One map pack due to file conflicts or something
blacklisted_bigone_maps = ['afraid-of-monsters']

# maps that should be ignored since they're older versions of something, but are kept on the DB for historical purposes
blacklisted_maps = ['afraid-of-monsters']

all_maps = []
default_content = []
work_dir = os.getcwd()
map_list_fname = 'maplist.txt'
link_rules_fname = 'link_rules.txt'
default_content_fname = 'resguy_default_content.txt'
map_download_dir = 'downloads'
map_pool_dir = 'content_pool'
old_pool_dir = 'old_content' # old versions of files go here
bigone_dir = 'bigone'
bifone_extras_dir = 'bigone_extras'
map_repack_dir = os.path.join(map_download_dir, 'repack')
map_pack_dir = os.path.join(map_download_dir, 'map_packs')
cache_dir = 'cache'
logs_dir = 'logs'
map_cache_dir = os.path.join(cache_dir, 'maps')
map_pack_cache_dir = os.path.join(cache_dir, 'map_packs')
page_cache_dir = os.path.join(cache_dir, 'pages')
zip_level = "-mx1" # "-mx1"
zip_type = "zip" # "7z"
file_permissions = stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH
dom = None
sound_exts = ['aiff', 'asf', 'asx', 'dls', 'flac', 'fsb', 'it', 'm3u', 'midi', 'mid', 'mod', 'mp2', 'pls', 
			  's3m', 'vag', 'wax', 'wma', 'xm', 'wav', 'ogg', 'mp3', 'au'
			  ]
valid_exts = ['bsp', 'mdl', 'spr', 'res', 'txt', 'tga', 'bmp', 'conf', 'gmr', 
			  'gsr', 'wad', 'cfg', 'as', 'save'
			  ] + sound_exts

pool_json = {}
map_json = {}
link_rules = {}
master_json = collections.OrderedDict({})
master_json_name = 'data.json'
pool_json_name = 'pool.json'
bigone_json_name = 'bigone.json'
in_progress_name = "UPDATE_IN_PROGRESS"

link_json = {}
link_json_name = os.path.join(cache_dir, 'links.json')

LOG_MOVED = 1
LOG_ADDED = 2
LOG_INVALID_EXT = 3
LOG_INVALID_LOC = 4
LOG_WEIRD_LOC = 5
LOG_OVERWRITE = 6
LOG_NOT_NEEDED = 7
LOG_DUPLICATE = 8
LOG_RECOVERED = 9
LOG_RENAMED = 10

LOG_BIT_EXTRA = 256

LOG_BIT_MASK = 256

# Hide the fact that we're a bot (not very nice, but otherwise we can't download certain maps like AOMDC)
opener = urllib.request.build_opener()
opener.addheaders = [('User-Agent','Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.1 Safari/603.1.30')]
urllib.request.install_opener(opener)
		  
def read_cached_page(file):
	if os.path.isfile(file):
		c = open(file, 'rb')
		contents = c.read()
		c.close()
		if len(contents) > 0:
			date = datetime.utcfromtimestamp( int(os.path.getmtime(file)) )
			print("Using cached page (%s)" % date.strftime("%Y/%m/%d %H:%M UTC") )
			return contents
		else:
			os.remove(file)
	return ''
		

def get_map_urls(mapname, is_map_pack=False, skip_cache=False):
	global dom
	global use_cache
	global map_json
	global link_json
	global page_cache_dir
	
	dl_type = 'mappack' if is_map_pack else 'map'
	cache_path = os.path.join(page_cache_dir, '%s_%s.html' % (dl_type, safe_map_name(mapname))) 
	thumb_path = os.path.join(page_cache_dir, 'img', '%s_%s.jpg' % (dl_type, safe_map_name(mapname))) 
	
	page_contents = read_cached_page(cache_path) if not skip_cache else ''
	
	if not len(page_contents):
		page_contents = ''
		try:
			page_contents = read_url_safe("%s/%s:%s" % (domain_name, dl_type, mapname))
		except urllib.error.HTTPError as e:
			print(e)
			return []
		c = open(cache_path, 'wb')
		c.write(page_contents)
		c.close()
	map_json['scrape_date'] = int(os.path.getmtime(cache_path))
	
	dom = html.fromstring(page_contents)
	links = dom.cssselect('#page-content div.dl a')
	
	# download the thumbnail
	if skip_cache:
		thumb = dom.cssselect(".gallery-box .gallery-item img")
		
		if len(thumb) == 0:
			print("Page has no images: %s" % mapname)
		else:
			thumb = thumb[0]
			file_contents = ''
			try:
				file_contents = read_url_safe(thumb.attrib['src'])
			except urllib.error.HTTPError as e:
				print(e)
				return []
				
			if not os.path.exists(os.path.dirname(thumb_path)):
				os.makedirs(os.path.dirname(thumb_path))
				
			c = open(thumb_path, 'wb')
			c.write(file_contents)
			c.close()
	
	use_idx = -1
	if mapname in link_rules:
		use_idx = link_rules[mapname]
		print("Forcing link %s of %s" % (use_idx, len(links)))

	ret = []
	idx = -1
	for link in links:
		if 'href' not in link.attrib:
			continue
		old_href = href = link.attrib['href']
		if href.startswith('javascript') or href.startswith('/map:') or href.startswith('/help:') or \
		   href.lower().startswith('#feedback') or href == 'http://www.svencoop.com/support.php':
			continue
			
		idx += 1
		if use_idx != -1:
			if idx != use_idx:
				continue
			print("Link rules says we should use this link: %s" % href)
			
		if old_href in link_json:
			# Use cached direct link if possible
			href = link_json[href]
			print("Using cached link: %s" % href)
		else:
			# Get direct link from download link
			if 'dropbox.com' in href:
				# Add dl=1 to link to bypass download page
				href = href.split('?')[0] + '?dl=1'
				# UPDATE 11/2017: This no longer works. You need to use their API now I guess.
				print("Dropbox links not supported")
				continue
			if 'gamebanana.com' in href:
				try:
					# go through the download pages to get the REAL link
					print("Searching through GameBanana download pages...")
					at_second_page = '/download/' in href
					gbdom = html.fromstring(read_url_safe(href))
					href = ''
					dlpage = gbdom.cssselect('#DownloadModule > div > div > a')
					direct_link = gbdom.cssselect('#FilesModule .DownloadOptions > a')
					
					if len(direct_link) > 0:
						href = direct_link[0].attrib['href']
					elif len(dlpage) > 0 or at_second_page:
						if not at_second_page:
							dlpage = dlpage[0].attrib['href']
							gbdom = html.fromstring(read_url_safe(dlpage))
						dllink = gbdom.cssselect('#OfficialDirectDownload')
						if len(dllink) > 0:
							href = dllink[0].attrib['href']
				except Exception as e:
					print(e)
			if 'mediafire.com' in href:
				print("Link to mediafire ignored (bots aren't allowed to download from there).")
				continue
			if 'drive.google.com' in href:
				print("Google Drive links not supported")
				continue
			if 'onedrive.live.com' in href:
				print("Microsoft One Drive links not supported")
				continue
			
		if old_href != href:
			link_json[old_href] = href
			with open(link_json_name, 'w') as outfile:
				json.dump(link_json, outfile)
					
		if len(href):
			ret.append(href)
		else:
			print("Failed to get direct link from %s" % link.attrib['href'])
	return ret
		
		
# assumes dom is set
def get_bsp_filenames():
	global dom
	
	if dom is None:
		print("Failed to get BSP filenames (no dom)")
		return []

	for i in range(100):
		fname_label = dom.cssselect('.wiki-content-table > tr:nth-child(%s) > td:nth-child(1) > strong' % (i+1))
		if len(fname_label) > 0:
			fname_label = fname_label[0].text_content()
			if '.bsp' in fname_label:
				bsps = dom.cssselect('.wiki-content-table > tr:nth-child(%s) > td:nth-child(2)' % (i+1))
				if (len(bsps)) > 0:
					bsps = bsps[0].text_content()
					return bsps.split(', ')
				else:
					print("bsp section didn't have any names in it")
		else:
			break

	print("Failed to get BSP filenames")

def get_map_info():	
	global dom
	
	if dom is None:
		print("Failed to get map info (no dom)")
		return {}

	info = {}
	title = dom.cssselect('#page-title')
	if len(title) > 0:
		info['title'] = title[0].text_content()
	else:
		print("Failed to get title from DOM")
		
	rev = dom.cssselect('#page-info')
	if len(rev) > 0:
		rev = rev[0].text_content()
		rev_int = int( rev[rev.find("page revision: ") + len("page revision: "):rev.find(",")] )
		info['rev'] = rev_int
		
		try:
			# not all times have the comma
			rev_time = rev[rev.find("last edited: ") + len("last edited: "):].replace(",", "")
			rev_time = datetime.strptime(rev_time, "%d %b %Y %H:%M").timetuple()
			rev_time = int(time.mktime(rev_time) / 60)
			info['rev_time'] = rev_time
		except Exception as e:
			print(e)
			print("Failed to parse revision time <%s>" % rev_time)
	else:
		print("Failed to get map revision from DOM")
		
	for i in range(100):
		fname_label = dom.cssselect('#page-content .actualcontent .wiki-content-table > tr:nth-child(%s) > td:nth-child(1) > strong' % (i+1))
		if len(fname_label) > 0:
			fname_label = fname_label[0].text_content()
			if 'Author' in fname_label or 'Converted by' in fname_label:
				author = dom.cssselect('#page-content .actualcontent .wiki-content-table > tr:nth-child(%s) > td:nth-child(2)' % (i+1))
				if len(author) > 0:
					info['author'] = author[0].text_content()
		
		else:
			break
	if 'author' not in info:
		print("Failed to get map author from DOM")
	
	info['tags'] = []
	map_tags = dom.cssselect('#page-content .tags_in_body > a')
	for tag in map_tags:
		info['tags'].append(tag.text_content())
		
	info['rating'] = 0
	info['votes'] = 0
	map_rating = dom.cssselect('#page-content .actualcontent2 > p > strong')
	map_votes = dom.cssselect('#page-content .actualcontent2 > p > span')
	if len(map_rating) > 0 and len(map_votes) > 0:
		info['rating'] = float(map_rating[0].text_content())
		info['votes'] = int(map_votes[0].text_content().split()[0][1:])
	else:
		print("Failed to get map rating from DOM")
	
	regex = '(january|february|march|april|may|june|july|august|september|october|november|december)+\s*\d\d,\s*\d\d\d\d'
	for i in range(100):
		fname_label = dom.cssselect('#page-content .actualcontent .wiki-content-table > tr:nth-child(%s) > td:nth-child(1) > strong' % (i+1))
		if len(fname_label) > 0:
			fname_label = fname_label[0].text_content()
			if 'Date of release' in fname_label:
				dates = dom.cssselect('#page-content .actualcontent .wiki-content-table > tr:nth-child(%s) > td:nth-child(2)' % (i+1))
				if len(dates) > 0:
					date = re.search(regex, dates[0].text_content(), re.IGNORECASE)
					if date:
						info['release_date'] = date.group(0)
		
		else:
			break
	if 'release_date' not in info:
		print("Failed to get map release date from DOM")
	
	return info
	
def map_zip_exists(map):
	global zip_type
	safe_name = safe_map_name(map)
	zip = os.path.join(map_download_dir, "%s.%s" % (safe_name, zip_type))
	return os.path.isfile(zip)
	
def is_map_outdated(map):
	global page_cache_dir
	
	zip_deleted = not map_zip_exists(map)
	
	#if map in master_json and ('failed' in master_json[map] or 'default' in master_json[map]):
	#if map in master_json and ('default' in master_json[map]):
	#	zip_deleted = False
	page_contents = ''
	try:
		page_contents = read_url_safe("%s/map:%s" % (domain_name, map))
	except urllib.error.HTTPError as e:
		print(e)
		if "404" in "%s" % e:
			print("The DB page was deleted!")
			return False
		else:
			time.sleep(1)
			return is_map_outdated(map)		

	mdom = html.fromstring(page_contents)

	rev = mdom.cssselect('#page-info')
	if len(rev) > 0:
		rev = rev[0].text_content()
		rev = int( rev[rev.find("page revision: ") + len("page revision: "):rev.find(",")] )
		
		if zip_deleted or map not in master_json or 'rev' not in master_json[map] or master_json[map]['rev'] < rev:
			# update cached page
			cache_path = os.path.join(page_cache_dir, 'map_%s.html' % safe_map_name(map)) 
			os.makedirs(page_cache_dir, exist_ok=True)
			c = open(cache_path, 'wb')
			c.write(page_contents)
			c.close()
			return True
	else:
		print("OH NO LAST EDIT DIV IS GONE")
	
	return False
	
def delete_map_from_json(map):
	global master_json
	
	print("Removing map: %s" % map)
	remove_pool_references(map)
	num_refs_removed = remove_pool_references(map)
	if map in master_json:
		del master_json[map]
		with open(master_json_name, 'w') as outfile:
			json.dump(master_json, outfile)
		print("Deleted from data.json")
	print("Removed %s pool file references" % num_refs_removed)
	
def update_map_list():
	global master_json
	global all_maps
	global master_json_name
	
	print("")
	print("Getting list of all maps...")
	print("")
	
	old_map_list = []
	if os.path.isfile(map_list_fname):
		with open(map_list_fname) as f:
			old_map_list = f.read().splitlines()
	new_maps = []
	removed_maps = []
	
	all_maps = []
	
	page = 1
	max_page = -1
	while max_page == -1 or page <= max_page:
		root = html.fromstring(read_url_safe("%s/tag:all/p/%s" % (domain_name, page)))
		
		# get max page if unknown
		if max_page == -1:
			page_num = root.cssselect('#page-content div.lister-container-wrap div.pager > span.pager-no')
			page_num = int(page_num[0].text_content().split()[-1])
			if page_num < 0 or page_num > 100:
				print("Error: Max page parsed incorrectly or last page is >100. Exiting.")
				break
			else:
				max_page = page_num
				
		print("Check page %s of %s" % (page, max_page))
		
		links = root.cssselect('#page-content div.lister-container-wrap div.lister-item-title > p > a')
		for link in links:
			href = link.attrib['href']
			map = href.split('/map:')[-1]
			all_maps.append(map)
			if map not in old_map_list:
				new_maps.append(map)
				print("New map: %s" % map)
			#print( href )
			
		page += 1

	for map in old_map_list:
		if map not in all_maps:
			removed_maps.append(map)
			delete_map_from_json(map)
		
	f = open('maplist.txt', 'wb')
	for c in all_maps:
		f.write(('%s\r\n' % c).encode("utf-8"))
	f.close()
	
	print("Map list updated. %s maps added. %s maps removed." % (len(new_maps), len(removed_maps)))
	
	return new_maps
	
# check that the archive is actually an archive
def validate_archive(archive_path):
	global debug_zip
	debug_zip = False

	ext = archive_path.split('.')[-1].lower()
	
	# check if we downloaded a 404 page
	sz = os.path.getsize(archive_path)
	if sz < 1024*1024: # no 404 page should be more than a megabyte
		with open(archive_path) as file:
			try:
				contents = file.read()
				raise Exception("Downloaded text file instead of archive")
			except UnicodeDecodeError as e:
				# probably a binary file
				pass
	
	if ext == '7z':
		zip_archive_path = archive_path.replace('\\', '/')
		program_name = "7za.exe" if platform.system() == "Windows" else "7za"
		try:
			with open(os.devnull, 'w') as devnull:
				args = [program_name, 'l', zip_archive_path]
				zip_stdout=None if debug_zip else devnull
				subprocess.check_call(args, stdout=zip_stdout)
		except Exception as e:
			if debug_zip:
				print("Failed to open %s" % archive_path)
				print(e)
			return False
	elif ext == 'bsp':
		return True
	else:
		save = os.dup(1), os.dup(2)
		null_fds = [os.open(os.devnull, os.O_RDWR) for x in [0,1]]
		
		try:
			if not debug_zip:
				# suppress stdout/stderr
				os.dup2(null_fds[0], 1)
				os.dup2(null_fds[1], 2)

			with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
				with open(os.devnull, "w") as f2, contextlib.redirect_stderr(f2):
					patoolib.list_archive(archive_path, verbosity=0, interactive=False)
		except Exception as e:
			if not debug_zip:
				# restore stdout/stderr
				os.dup2(save[0], 1)
				os.dup2(save[1], 2)
				os.close(null_fds[0])
				os.close(null_fds[1])
				os.close(save[0])
				os.close(save[1])
				pass
			if debug_zip or True:
				print("Failed to open %s" % archive_path)
				print(e)
			return False
			
		if not debug_zip:
			# restore stdout/stderr
			os.dup2(save[0], 1)
			os.dup2(save[1], 2)
			os.close(null_fds[0])
			os.close(null_fds[1])
			os.close(save[0])
			os.close(save[1])
	return True

def extract_archive(archive_path, out_path, bsp_name=""):
	global debug_zip
	global unpack_nested
	
	if not os.path.exists(out_path):
		os.makedirs(out_path)
		
	ext = archive_path.split('.')[-1].lower()
	
	if ext == '7z':
		zip_out_path = out_path.replace('\\', '/')
		zip_archive_path = archive_path.replace('\\', '/')
		program_name = "7za.exe" if platform.system() == "Windows" else "7za"
		try:
			with open(os.devnull, 'w') as devnull:
				args = [program_name, 'x', '-aos', '-o%s' % zip_out_path, zip_archive_path]
				zip_stdout=None if debug_zip else devnull
				subprocess.check_call(args, stdout=zip_stdout)
		except Exception as e:
			if debug_zip:
				print("Failed to unpack %s (maybe dl'd a 404 page?)" % archive_path)
				print(e)
			return False
	elif ext == 'bsp':
		# I saw someone just upload a bsp by itself. We can just copy these.
		fname = os.path.basename(archive_path)
		if bsp_name:
			fname = bsp_name + ".bsp"
		shutil.copy(archive_path, os.path.join(out_path, fname))
	else:
		save = os.dup(1), os.dup(2)
		null_fds = [os.open(os.devnull, os.O_RDWR) for x in [0,1]]
		
		try:
			if not debug_zip:
				# suppress stdout/stderr
				os.dup2(null_fds[0], 1)
				os.dup2(null_fds[1], 2)

			with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
				with open(os.devnull, "w") as f2, contextlib.redirect_stderr(f2):
					patoolib.extract_archive(archive_path, outdir=out_path, verbosity=0)
		except Exception as e:
			if not debug_zip:
				# restore stdout/stderr
				os.dup2(save[0], 1)
				os.dup2(save[1], 2)
				os.close(null_fds[0])
				os.close(null_fds[1])
				os.close(save[0])
				os.close(save[1])
				pass
			if debug_zip or True:
				print("Failed to unpack %s (maybe dl'd a 404 page?)" % archive_path)
				print(e)
			return False
		
		if not debug_zip:
			# restore stdout/stderr
			os.dup2(save[0], 1)
			os.dup2(save[1], 2)
			os.close(null_fds[0])
			os.close(null_fds[1])
			os.close(save[0])
			os.close(save[1])
			
	nested_archives = list(find_files(out_path, '*.rar'))
	nested_archives += list(find_files(out_path, '*.zip'))
	nested_archives += list(find_files(out_path, '*.7z'))
	if unpack_nested and len(nested_archives) > 0:
		nested = nested_archives[0]
		print('Unpacking nested archive: %s' % nested)
		os.remove(archive_path)
		shutil.move(nested, archive_path)
		shutil.rmtree(out_path)
		return extract_archive(archive_path, out_path)
		
	return True
	
def download_map_pack(packname):
	os.makedirs(map_pack_dir, exist_ok=True)
	os.makedirs(map_pack_cache_dir, exist_ok=True)
	
	safe_pack_name = safe_map_name(packname)
	
	pack_path = os.path.join(map_pack_dir, safe_pack_name)
	
	if packname == 'svencoop':
		file_name = os.path.join(map_pack_cache_dir, 'svencoop.7z')
		got_it = os.path.isfile(file_name)
	else:
		links = get_map_urls(packname, True)
		got_it = False
		file_name=''
		for link in links:
			ext = link.split('.')[-1]
			if len(ext) < 1:
				print("File with no extension!")
				continue
				
			file_name = os.path.join(map_pack_dir, '%s.%s' % (safe_pack_name, ext))
				
			# Check if we already got this one
			cache_archive_path = os.path.join(map_pack_cache_dir, '%s.%s' % (safe_pack_name, ext))
			if use_cache and os.path.isfile(cache_archive_path):
				shutil.copy(cache_archive_path, file_name)
				got_it = True
				print("Using cached package")
				break
				
			print("Downloading %s from: %s" % (safe_pack_name, link))
			
			try:
				download_file_safe(link, file_name)
				if use_cache:
					shutil.copy(file_name, cache_archive_path)
				got_it = True
				break
			except ValueError as e:
				print(e)
				print("Skipping invalid URL: %s" % link)
			except Exception as e:
				print("Download failed: %s" % e)		
	
	if got_it:
		print("Unpacking %s" % file_name)
		if not extract_archive(file_name, os.path.join(map_pack_dir, safe_pack_name)):
			return False
		os.remove(file_name)
		
		# fix up paths
		all_files = find_files(pack_path, '*')
		for pack_file in all_files:
			pack_file = pack_file.split(pack_path)[-1][1:]
			fix_asset(pack_file, repack_dir=pack_path)
		return True
		
	return False
	
def recover_missing_file(pack_path, file):
	global verbose
	
	file = file.replace("\\","/")
	parts = file.split("/")
	
	tree = pool_json
	for part in parts:
		if part in tree:
			tree = tree[part]
		else:
			tree = None
			break
	if not tree:
		if verbose:
			print("Missing file: %s" % file)
		
		if os.path.isfile(os.path.join(map_pool_dir, file)):
			# File exists, but no map in the DB includes it anymore
			print("file not in pool.json but it DOES exist: %s" % file)
			return False
		else:
			return False
	
	pool_file = os.path.join(map_pool_dir, file)
	if not os.path.isfile(pool_file):
		print("Missing pool file: %s" % pool_file)
		return False
		
	dest_file = os.path.join(pack_path, file)
	
	if not os.path.exists(os.path.dirname(dest_file)):
		os.makedirs(os.path.dirname(dest_file))
	shutil.copy(pool_file, dest_file)
	os.chmod(dest_file, file_permissions)
	
	if verbose:
		print("Recovered missing file: %s" % file)	
	return True
	
# TODO: Generate all res files in series at once (big speed boost for AOM series)
def gen_res_file(pack_path, mapname, recover_missing=True):
	res_content = []

	res_file = os.path.join('maps', '%s.res' % mapname)
	res_path = os.path.join(pack_path, res_file)
	
	if os.path.exists(res_path) and not os.path.exists(res_path + ".old"):
		shutil.move(res_path, res_path + ".old")
	if os.path.exists(res_path + '2'):
		os.remove(res_path + '2')
	if os.path.exists(res_path + '3'):
		os.remove(res_path + '3')
	
	shutil.copy(default_content_fname, pack_path + "/" + default_content_fname)
	os.chdir(pack_path)
	program_path = os.path.join(work_dir,'resguy' + ('.exe' if platform.system() == "Windows" else ""))
	resguy_output = ''
	try:
		with open(os.devnull, 'w') as devnull:
			args = [program_path, mapname, '-extra2', '-missing3', '-printskip', '-icase']
			try:
				output = subprocess.check_output(args)
			except subprocess.CalledProcessError as e:
				output = e.output
				
			output = output.decode('ascii', 'ignore')
			if platform.system() != "Windows":
				output = output.replace('\n', '\r\n')
				
			output = output[output.find('Generating .res file'):] # Skip "Loading default content" and control chars
				
			if 'resguy_log' not in map_json:
				resguy_output = ''
			else:
				resguy_output = map_json['resguy_log'] + '\r\n' + ('- ' * 30) + '\r\n\r\n'
			resguy_output += output
			#print(output)
	except Exception as e:
		print(e)
	os.chdir(work_dir)
	
	if platform.system() != "Windows" and os.path.exists(res_path):
		# Convert unix-style line endings to windows-style
		fileContents = open(res_path,"r").read()
		f = open(res_path, "w", newline="\r\n")
		f.write(fileContents)
		f.close()
	
	# Log missing files & try to find replacements
	missing_res_path = res_path + '3'
	num_missing = 0
	num_recover = 0
	missing_files = []
	if os.path.exists(missing_res_path):
		with open(missing_res_path) as f:
			missing_files = f.read().splitlines()
		for f in missing_files:
			if recover_missing_file(pack_path, f):
				num_recover += 1
			else:
				#num_missing += 1
				map_json['missing_files'].add(f.lower())
	if num_recover > 0:
		if 'recover' in map_json:
			map_json['recover'] += num_recover
		else:
			map_json['recover'] = num_recover
		if os.path.isfile(res_path):
			os.remove(res_path)
		if os.path.isfile(missing_res_path):
			os.remove(missing_res_path)
		if os.path.isfile(res_path + '2'):
			os.remove(res_path + '2')
		return gen_res_file(pack_path, mapname, False)
		
	map_json['resguy_log'] = resguy_output
	
	if os.path.exists(res_path):
		with open(res_path) as f:
			res_content = f.read().splitlines()
		res_content = [x for x in res_content if len(x) and x[0] != '/']
		
	
	# Log differences between .res files
	
	if 'res_diff' not in map_json:
		map_json['res_diff'] = collections.OrderedDict({})
	map_json['res_diff'][mapname] = []
	
	if os.path.exists(res_path) and os.path.exists(res_path + ".old"):
		with open(res_path) as f:
			new_res = f.read().splitlines()
		with open(res_path + ".old", "rb") as f:
			old_res = f.read().decode("utf-8", "ignore").splitlines()
			
		new_res = [x.strip() for x in new_res]
		old_res = [x.strip() for x in old_res]
		new_res = [x for x in new_res if len(x) and x[0] != '/']
		old_res = [x for x in old_res if len(x) and x[0] != '/']

		added = [x for x in new_res if x not in old_res]
		for entry in added:
			map_json['res_diff'][mapname].append('+' + entry)
			
		removed = [x for x in old_res if x not in new_res]
		for entry in removed:
			map_json['res_diff'][mapname].append('-' + entry)
	elif os.path.exists(res_path):
		with open(res_path) as f:
			new_res = f.read().splitlines()
		new_res = [x for x in new_res if len(x) and x[0] != '/']
		
		for entry in new_res:
			map_json['res_diff'][mapname].append('+' + entry)
	elif os.path.exists(res_path + '.old'):
		with open(res_path + '.old') as f:
			old_res = f.read().splitlines()
		old_res = [x for x in old_res if len(x) and x[0] != '/']
		
		for entry in old_res:
			map_json['res_diff'][mapname].append('-' + entry)
			
	return res_content
	
def repack_map_from_map_pack(mapname, bsp_filenames, packname):
	global debug_zip
	global zip_level
	global zip_type
	global include_readmes
	
	safe_mapname = safe_map_name(mapname)
	safe_pack_name = safe_map_name(packname)
	
	pack_path = os.path.join(map_pack_dir, safe_pack_name)
	if not os.path.exists(pack_path):
		if not download_map_pack(packname):
			print("Failed to pack %s. Map pack not downloaded." % safe_mapname)
			return False
		
	# Check to make sure the bsps actually exist
	new_bsp_filenames = []
	mapDir = os.path.join(pack_path,'maps')
	map_dir_files_lower = [x.lower() for x in os.listdir(mapDir)]
	for bsp in bsp_filenames:
		mapExists = False
		searchMap = '%s.bsp' % bsp
		for file in os.listdir(mapDir):
			if file.lower() == searchMap:
				new_bsp_filenames.append(file[:-4])
				mapExists = True
				break
		if not mapExists:
			print("Warning: %s.bsp does not exist!" % bsp)
			all_bsps = find_files(os.path.join(pack_path, 'maps'), '*.bsp')
			for b in all_bsps:
				if bsp.lower() in b.lower():
					b = b.split(os.sep)[-1].replace('.bsp', '')
					if b not in new_bsp_filenames:
						new_bsp_filenames.append(b)
						print("Packing map with similar filename: %s.bsp" % b)
	bsp_filenames = new_bsp_filenames
		
	pack_files = []
	map_json['missing_files'] = set()
	for bsp in bsp_filenames:
		res_file = os.path.join('maps', '%s.res' % bsp)
		res_path = os.path.join(pack_path, res_file)
		print("Finding content for %s.bsp" % bsp)
		content = []
		possible_content = [os.path.join('maps', '%s.bsp' % bsp),
							os.path.join('maps', '%s.cfg' % bsp),
							os.path.join('maps', '%s_skl.cfg' % bsp),
							os.path.join('maps', '%s_motd.txt' % bsp),
							os.path.join('maps', '%s_detail.txt' % bsp)]
							
		if include_readmes:
			possible_content.append(os.path.join('maps', '%s_readme.txt' % bsp))

		pack_path_files = [os.path.join('maps', x) for x in os.listdir(mapDir)]
		pack_path_files_lower = [x.lower() for x in pack_path_files]
		
		for c in possible_content:
			for p in pack_path_files:
				if p.lower() == c.lower():
					pack_files.append(p)
					break
		
		if include_readmes:
			# Rename old-style readmes
			old_readme_name = os.path.join('maps', '%s.txt' % bsp)
			new_readme_name = os.path.join('maps', '%s_readme.txt' % bsp)
			for p in pack_path_files:
				if p.lower() == old_readme_name.lower():
					if not os.path.exists(os.path.join(pack_path, new_readme_name)):
						shutil.copyfile(os.path.join(pack_path, p), os.path.join(pack_path, new_readme_name))
						pack_files.append(new_readme_name)
						if verbose:
							print("Renaming old-style readme")
					break
					
		gen_res_file(pack_path, bsp)
				
		if os.path.isfile(res_path):
			pack_files.append(res_file)
			res_lines = []
			with open(res_path) as f:
				res_lines = f.read().splitlines()
			
			# Add server-only files to list so they aren't removed from the archive
			if os.path.exists(res_path + '2'):
				#print("got res2 for %s" % bsp)
				with open(res_path + '2' ) as f:
					res_lines += f.read().splitlines()
			#else:
				#print("no res2 for %s" % bsp)
			
			for line in res_lines:
				line = line.strip()
				if not line or line[0] == '/':
					continue # skip comments
				
				line_path = line.replace('/', os.sep)
				if os.path.isfile(os.path.join(pack_path,line_path)):
					pack_files.append(line_path)
				else:
					print("Res file lists non-existant file: %s" % line_path)
					
		

	map_json['missing'] = len(map_json['missing_files'])
	map_json.pop('missing_files', None)
	
	# remove duplicates
	pack_files_lower = set([x.lower() for x in pack_files])
	new_pack_files = []
	for k in pack_files_lower:
		for j in pack_files:
			if j.lower() == k:
				new_pack_files.append(j)
				break
	pack_files = new_pack_files
		
	# write all files to list
	list_file = os.path.join(pack_path, 'repack_file_list.txt')
	f = open(list_file, 'wb')
	for c in pack_files:
		os.chmod(os.path.join(pack_path, c), file_permissions)
		f.write(('%s\r\n' % c).encode("utf-8"))
	f.close()
	
	map_json['new_files'] = list_to_tree( [x.replace('\\', '/') for x in pack_files] )
	map_json['old_files'] = {'Found only in the %s' % packname: 0}
	
	# Create archive
	out_name = '%s.%s' % (safe_mapname, zip_type)
	out_path = os.path.join(map_download_dir, out_name)
	if os.path.isfile(out_path):
		os.remove(out_path)
	
	os.chdir(pack_path)
	program_path = os.path.join(work_dir,'7za.exe') if platform.system() == "Windows" else "7za"
	try:
		print("Compressing %s..." % out_name)
		with open(os.devnull, 'w') as devnull:
			args = [program_path, 'a', zip_level, '-t%s' % zip_type, '-mmt', '-scsUTF-8', '../../%s' % out_name, '@repack_file_list.txt']
			zip_stdout=None if debug_zip else devnull
			subprocess.check_call(args, stdout=zip_stdout)
		os.remove('repack_file_list.txt')
	except Exception as e:
		print(e)
	os.chdir(work_dir)
	
	map_json['map_pack'] = packname
	map_json['new_size'] = os.path.getsize(out_path);
	
	return True

# set default file/folder permissions recursively
def fix_file_perms(path):
	for subdir, dirs, files in os.walk(path):
		for dir in dirs:
			os.chmod(os.path.join(subdir, dir), stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
		for file in files:
			os.chmod(os.path.join(subdir, file), stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
	
def download_map(mapname, skip_cache=False):
	global use_cache
	global map_json
	
	os.makedirs(map_download_dir, exist_ok=True)
	os.makedirs(map_cache_dir, exist_ok=True)
		
	safe_fname = safe_map_name(mapname)
	links = get_map_urls(mapname)
	bsp_filenames = get_bsp_filenames()
	info = get_map_info()
	
	map_json['title'] = info['title'] if 'title' in info else '???'
	map_json['author'] = info['author'] if 'author' in info else '???'
	map_json['release_date'] = info['release_date'] if 'release_date' in info else '???'
	map_json['rev'] = info['rev'] if 'rev' in info else '???'
	map_json['rev_time'] = info['rev_time'] if 'rev_time' in info else '0'
	map_json['tags'] = info['tags']
	map_json['rating'] = info['rating']
	map_json['votes'] = info['votes']
	
	if len(links) == 0:
		print("%s has no download links!" % mapname)
		map_json['failed'] = True
		return True
	
	special_case = False
		
	ext=''
	map_pack=''
	
	for link in links:
		if '/mappack:' in link:
			map_pack = link.split('/mappack:')[-1]
			continue
		if '/mod:sven-co-op' in link:
			print("%s is included with the game (according to the DB)." % mapname)
			map_json['default'] = True
			#map_pack = 'svencoop' # special pack that's really just the default svencoop folder
			return
	
		ext = link.split('.')[-1].split('?')[0]
		if len(ext) < 1:
			print("File with no extension!")
			continue
			
		if ext.lower() == 'exe':
			print("EXE file not supported")
			continue
			
		if len(ext) > 3:
			ext = '7z'
			print("File extension unknown! Let's look at the HTTP header...")
			try:
				headers = requests.head(link, timeout=10).headers
				if 'Location' in headers:
					ext = headers['Location'].split('.')[-1].split('?')[0]
					if len(ext) < 1 or ext.lower() == 'exe' or len(ext) > 3:
						print("Failed to get an extension from location: %s" % headers['Location'])
						continue
					else:
						print("Extension seems to be %s" % ext)
			except:
				print("Failed to get an extension from link: %s" % link)
				continue
			
		file_name = os.path.join(map_download_dir, '%s.%s' % (safe_fname, ext))
		bsp_name = bsp_filenames[0] if bsp_filenames else mapname
		
		# Check if we already got this one
		cache_archive_path = os.path.join(map_cache_dir, '%s.%s' % (safe_fname, ext))
		if use_cache and os.path.isfile(cache_archive_path):
			if skip_cache and not force_zip_cache:
				# delete and redownload
				os.remove(cache_archive_path)
			else:
				print("Using cached package")
				shutil.copy(cache_archive_path, file_name)
				try:
					return not repack_map(mapname, ext, bsp_name)
				except TypeError as e:
					print("Failed to extract cached package: %s "% e)
					#os.remove(cache_archive_path)
			
			
		print("Downloading %s from: %s" % (mapname, link))
		
		try:	
			download_file_safe(link, file_name)
			if use_cache:
				shutil.copy(file_name, cache_archive_path)
			try:
				return not repack_map(mapname, ext, bsp_name)
			except TypeError as e:
				print("Failed to extract package (maybe got a 404 page?)")
				print(e)
				if os.path.isfile(cache_archive_path):
					os.remove(cache_archive_path)
				
		except ValueError as e:
			traceback.print_exc()
			print("Skipping invalid URL: %s" % link)
		except Exception as e:
			print("Failed to download map from link: %s" % link)
			print("File to save: %s" % file_name)
			print(e)

	if len(map_pack) > 0:
		print("%s is only found in the '%s' map pack." % (mapname, map_pack))
		repack_map_from_map_pack(mapname, bsp_filenames, map_pack)
		special_case = True
	else:
		print("Failed to download %s!" % mapname)
		map_json['failed'] = True
		return True
	
	return special_case
	
def find_files(directory, pattern):
	import os, fnmatch
	for root, dirs, files in os.walk(directory):
		for basename in files:
			if fnmatch.fnmatch(basename.lower(), pattern):
				filename = os.path.join(root, basename)
				yield filename
				
def fix_asset_capitalization(path, rename=False, repack_dir=map_repack_dir):
	# correct the destination path
	old_parts = path.split(os.sep)
	new_parts = path.split(os.sep)
	if len(new_parts) > 1:
		new_parts[0] = new_parts[0].lower() # All content directorys at root level should be lower-case
		if rename and old_parts[0] != new_parts[0]:
			os.rename(os.path.join(repack_dir, old_parts[0]), os.path.join(repack_dir, new_parts[0]))
	if new_parts[0] in ['maps', 'gfx', 'scripts'] and len(new_parts) > 2:
		# subdirectories in here ('maps/graphs', 'gfx/env', 'gfx/detail', 'scripts/maps') should be lower-case
		new_parts[1] = new_parts[1].lower()
		if rename and old_parts[1] != new_parts[1]:
			os.rename(os.path.join(repack_dir, new_parts[0], old_parts[1]), os.path.join(repack_dir, new_parts[0], new_parts[1]))
	out_path = os.path.join(*new_parts)
	#if out_path != path:
	#	print("Lowercase: %s --> %s" % (path, out_path))
	return out_path
	
def get_asset_capitalization(path, start=map_repack_dir):
	'''Returns a unix-type case-sensitive path, works in windows and linux'''
	corrected_path = ''
	if path[-1] == '/':
		path = path[:-1]
	parts = path.split('/')
	cd = start

	for p in parts:
		if not os.path.exists(os.path.join(cd,p)): # Check it's not correct already
			listing = os.listdir(cd)

			cip = p.lower()
			cilisting = [l.lower() for l in listing]

			if cip in cilisting:
				l = listing[ cilisting.index(cip) ] # Get our real folder name
				cd = os.path.join(cd, l)
				corrected_path = os.path.join(corrected_path, l)
			else:
				print("UNABLE TO FIND: %s in %s" % (cip, cilisting))
				return False # Error, this path element isn't found
		else:
			cd = os.path.join(cd, p)
			corrected_path = os.path.join(corrected_path, p)

	return corrected_path
	
# Move assets to the right location and flag invalid assets
def fix_asset(path, repack_dir=map_repack_dir, bsp_filenames=[]):
	global valid_exts
	global verbose
	global file_permissions
	global map_json
		
	# Gets rid of any files that don't make sense where they are (e.g. a .bsp in the models folder)
	def file_makes_sense_in_location(path):
		path_parts = path.split(os.sep)
		ext = path.split('.')[-1].lower()
		
		if len(path_parts) > 1:
			if path_parts[0] == 'maps':
				if ext not in ['bsp', 'cfg', 'txt', 'gmr', 'gsr', 'conf', 'save', 'res']:
					return ext in ['nod', 'nrp'] and path_parts[1].lower() == 'graphs'
			if path_parts[0] == 'gfx':
				return ext == 'tga'
			if path_parts[0] == 'models':
				if ext not in ['mdl', 'txt', 'gmr']:
					return ext == 'bmp' and path_parts[1].lower() == 'player' and len(path_parts) == 4
			if path_parts[0] == 'sound':
				return ext in sound_exts or ext in ['txt', 'gsr']
			if path_parts[0] == 'sprites':
				return ext in ['spr', 'txt', 'gmr']
			if path_parts[0] == 'events':
				return ext == 'txt'
			if path_parts[0] == 'scripts':
				return True # you can use any file type you want in a script
		elif len(path_parts) == 1:
			return ext == 'wad'
			
		return True
					
	
	duplicate_file = [0] # should be a bool, but python has variable scope weirdness
	def move_asset(old_path, new_path):			
		if old_path == new_path:
			return new_path
			
		path = fix_asset_capitalization(new_path)
			
		if old_path.lower() == new_path.lower():
			# Don't move anything, just rename the folders
			old_parts = old_path.split(os.sep)
			new_parts = new_path.split(os.sep)
			for idx, part in enumerate(old_parts):
				if part != new_parts[idx]:
					old_name = os.path.join(repack_dir, *old_parts[:idx+1])
					new_name = os.path.join(repack_dir, *new_parts[:idx+1])
					print("RENAME: %s --> %s" % (old_name, new_name))
					if os.path.exists(new_name):
						# target dir already exists (e.g. "Maps" -> "maps")
						for item in os.listdir(old_name):
							shutil.move(os.path.join(old_name, item), os.path.join(new_name, item))
					else:
						shutil.move(old_name, new_name)
					
			return path
		
		
		if os.path.isfile(os.path.join(repack_dir, path)):
			# duplicate file
			duplicate_file[0] += 1
			return old_path
		
		if verbose:
			print("Moving:	   %s --> %s" % (old_path, new_path))
		
		old_path = os.path.join(repack_dir, old_path)
		new_path = os.path.join(repack_dir, path)
		new_dirs = os.path.dirname(new_path)
		if not os.path.exists(new_dirs):
			os.makedirs(new_dirs)
		shutil.move(old_path, new_path)
		
		return path
		
	parts = path.split(os.sep)
	out_path = path
		
	# Make sure path is valid (folders could have been renamed for other assets)
	if not os.path.exists(os.path.join(repack_dir, path)):
		out_path = path = fix_asset_capitalization(path)
		parts = path.split(os.sep)
		
	# Disable read-only attribute (can't delete or 7zip it otherwise)
	if out_path:
		os.chmod(os.path.join(repack_dir, out_path), file_permissions )
		
	ext = path.split('.')[-1].lower()
	
	if ext not in valid_exts:
		if verbose:
			print("Discarding: %s (RE: invalid extension)" % path)
		log_file_action(path, LOG_INVALID_EXT)
		return (path, False) # don't pack this file
		
	iswad = ext == 'wad'
	
	# Correct packs that have unnecesary parent folders ('svencoop/', 'Half-Life/SvenCoop/', etc.)
	for idx, part in enumerate(parts):
		if idx == 0:
			if part.lower() in ['maps', 'models', 'sound', 'sounds', 'sprites', 'gfx', 'scripts', 'events']:
				break # things like "sound/rng/morass_beta/sounds/" are ok
			continue
		if part.lower() in ['maps', 'models', 'sound', 'sounds', 'sprites', 'gfx', 'scripts', 'events'] or iswad:
			if part.lower() == 'maps':
				if parts[idx-1] == 'scripts':
					if idx-1 == 0:
						break # in this case it's ok for 'maps' not to be in the root
						
			out_path = parts[-1] if iswad else os.path.join(*parts[idx:])
			out_path = move_asset(path, out_path)
			break
			
	# Correct packs that dump everything in a random folder
	parts = out_path.split(os.sep)
	if len(parts) == 2 and parts[0] not in ['maps', 'models', 'sound', 'sounds', 'sprites', 'gfx', 'scripts', 'events', 'svencoop']:
		if ext in sound_exts:
			out_path = move_asset(path, os.path.join('sound', parts[1]))
		elif ext == 'mdl':
			out_path = move_asset(path, os.path.join('models', parts[1]))
		elif ext == 'tga':
			out_path = move_asset(path, os.path.join('gfx', 'env', parts[1]))
		elif ext == 'spr':
			out_path = move_asset(path, os.path.join('sprites', parts[1]))
		else:
			out_path = move_asset(path, os.path.join('maps', parts[1]))
		# TODO: Move event .txt into events/
			
	# Correct packs that just dump everything in the root
	if len(out_path) > 0 and len(parts) == 1 and not iswad:
		if ext in sound_exts:
			out_path = move_asset(path, os.path.join('sound', path))
		elif ext == 'mdl':
			out_path = move_asset(path, os.path.join('models', path))
		elif ext == 'tga':
			out_path = move_asset(path, os.path.join('gfx', 'env', path))
		elif ext == 'spr':
			out_path = move_asset(path, os.path.join('sprites', path))
		else:
			out_path = move_asset(path, os.path.join('maps', path))
		# TODO: Move event .txt into events/
		
	# People occasionally get this folder wrong (understandable since the other folders are plural)
	parts = out_path.split(os.sep)
	if len(parts) > 1 and parts[0].lower() == 'sounds':
		parts[0] = 'sound'
		out_path = move_asset(out_path, os.path.join(*parts))
		
	if duplicate_file[0]:
		# File wasn't moved because another file was already there (see afraid-of-monsters)
		if verbose:
			print("Discarding: %s (RE: duplicate file)" % path)
		log_file_action(path, LOG_DUPLICATE)
		#move_asset(out_path, path) # undo move
		return (out_path, False)
		
	if out_path != path:
		log_file_action(path, LOG_MOVED)
		
	out_path = fix_asset_capitalization(out_path, True)
		
	# After accounting for moves, remove it if it would still be in a non-standard folder 
	# (e.g. 'svencoop/extras/about_this_map.txt' --> 'extras/about_this_map.txt' = useless file)
	parts = out_path.split(os.sep)
	if len(parts) > 1 and parts[0] not in ['maps', 'models', 'sound', 'sprites', 'gfx', 'scripts', 'events']:
		if verbose:
			print("Discarding: %s (RE: not in a standard folder)" % path.encode('ascii', 'ignore').decode('ascii'))
		log_file_action(path, LOG_INVALID_LOC)
		#move_asset(out_path, path) # undo move
		return (out_path, False)
			
	if not file_makes_sense_in_location(out_path):
		if verbose:
			print("Discarding: %s (RE: unused / doesn't belong here)" % path)
		log_file_action(path, LOG_WEIRD_LOC)
		#move_asset(out_path, path) # undo move
		return (out_path, False)
		
	if out_path.replace('\\','/').lower() in default_content:
		if verbose:
			print("Discarding: %s (RE: overwrites default content)" % path)
		log_file_action(path, LOG_OVERWRITE)
		map_json["overwrites_default"] = True
		#move_asset(out_path, path) # undo move
		return (out_path, False)
		
	return (out_path, True)
	
def safe_map_name(mapname):
	for c in [':', '<', '>', '*', '/', '\\', '|', '"']:
		mapname = mapname.replace(c, '-')
	return mapname
	
def list_to_tree(files):
	tree = collections.OrderedDict({})
	
	files.sort()
	for file in files:
		parts = file.split('/')
		
		parent = tree
		for idx, node in enumerate(parts):
			if idx == len(parts) - 1:
				parent[node] = 0
				break
			else:
				if node not in parent:
					parent[node] = collections.OrderedDict({})
				parent = parent[node]
			
	return tree

def log_file_src(tree, file, src, erase=False, is_extra=False, is_conflict=False):
	file = file.replace(os.sep, '/')
	parts = file.split('/')
	prefix = '+' if is_extra else '-'
	if len(src) > 0:
		src = prefix + src
	
	parent = tree
	for idx, node in enumerate(parts):
		if idx == len(parts) - 1:
			if node in parent and not erase:
				if len(src) > 0 and src not in parent[node]['refs']:
					parent[node]['refs'].append(src)
					
				new_flags = parent[node]['flags'];
				if is_conflict:
					new_flags = new_flags | 1
				parent[node]['flags'] = new_flags
			else:
				path = os.path.join(map_pool_dir, *parts)
				if os.path.exists(path):
					date = int(os.path.getmtime(path))
					size = os.path.getsize(path)
					#md5 = hashlib.md5(open(path, 'rb').read()).hexdigest()
					crc = format( zlib.crc32(open(path, 'rb').read()), 'x' )
				else:
					print("Failed to log source for nonexistant file: %s " % path)
					date = 0
					size = 0
					crc = 0
				flags = 0;
				if is_conflict:
					flags += 1;				
				parent[node] = { 'refs': [src], 'date': date, 'sz': size, 'crc': crc, 'flags': flags }
			break
		else:
			if node not in parent:
				parent[node] = collections.OrderedDict({})
			parent = parent[node]
			
	return tree
	
def get_file_src(tree, file):
	file = file.replace(os.sep, '/')
	parts = file.split('/')
	empty = {'refs': [], 'date': '', 'sz': 0, 'crc': 0, 'flags': 0}
	
	parent = tree
	for idx, node in enumerate(parts):
		if idx == len(parts) - 1:
			if node in parent:
				return parent[node].copy()
			break
		else:
			if node not in parent:
				return empty
			parent = parent[node]
			
	return empty
	
def log_file_action(file, action, add_bits=False, new_files=False, reset_flags=False):
	global map_json
	global verbose
	
	key = 'new_files' if new_files else 'old_files'
	if key not in map_json:
		map_json[key] = {} # Map packs don't have old_files, but we'll store this data just in case
	tree = map_json[key]
	file = file.replace('\\', '/')
	
	parts = file.split('/')
	
	parent = tree
	for idx, node in enumerate(parts):
		
		nextKey = ''
		for key in parent:
			if key.lower() == node.lower():
				nextKey = key
		
		if idx == len(parts) - 1:
			if reset_flags:
				parent[nextKey] = 0
			if add_bits and nextKey:
				parent[nextKey] = parent[nextKey] | action
			else:
				parent[nextKey] = (parent.get(nextKey, 0) & LOG_BIT_MASK) + action # preserve flags
			break
		else:
			if not nextKey:
				#parent[node] = {} # Somehow this ruins everyting (try AOM)
				if verbose:
					print("Failed to log file action for %s\n" % file)
				return
			parent = parent[nextKey]
	
# Note: I'm a shit coder so a lot of this function is duplicated in repack_map_from_map_pack()
def repack_map(mapname, ext, bsp_name=""):
	global debug_zip
	global debug_repack
	global use_cache
	global zip_level
	global zip_type
	global map_json
	global include_extras
	global map_repack_dir
	global include_readmes

	safe_mapname = safe_map_name(mapname)
	archive_path = os.path.join(map_download_dir, '%s.%s' % (safe_mapname, ext))
	if not os.path.isfile(archive_path):
		print("%s not found. Repack cancelled." % archive_path)
		return False
	
	old_size = os.path.getsize(archive_path)
	
	print("Repacking %s..." % mapname)
	
	if os.path.exists(map_repack_dir):
		fix_file_perms(map_repack_dir)
		shutil.rmtree(map_repack_dir)
	
	if not os.path.exists(map_repack_dir):
		os.makedirs(map_repack_dir)
		
	if not extract_archive(archive_path, map_repack_dir, bsp_name=bsp_name):
		os.remove(archive_path)
		shutil.rmtree(map_repack_dir)
		raise TypeError
	
	fix_file_perms(map_repack_dir)
	
	no_issues = True
	
	# write all files to list
	all_files = list(find_files(map_repack_dir, '*'))
	
	parent_dir = map_repack_dir.replace('\\', '/') + '/'
	map_json['old_files'] = list_to_tree( [x.replace('\\', '/').replace(parent_dir, '') for x in all_files] )
	
	content = []
	content_map = {}
	extra_content = []
	for pack_file in all_files:
		pack_file = pack_file.split(map_repack_dir)[-1][1:]
		if pack_file == 'repack_file_list.txt':
			continue
		
		fixed_path = fix_asset(pack_file)
		if not fixed_path[1]:
			if 'svencoop' + os.sep + fixed_path[0].lower() != pack_file.lower():	# the 'svencoop' parent dir is common. Ignore that.
				if 'GameCfg.wc' not in pack_file and 'CmdSeq.wc' not in pack_file and 'Thumbs.db' not in pack_file: # These are commonly included
					no_issues = False
		if fixed_path[1]:
			content.append(fixed_path[0])
			content_map[fixed_path[0].lower()] = pack_file
		else: # file was deleted for some reason
			content_map[pack_file] = pack_file
			ext = pack_file.split('.')[-1].lower()
			if 'GameCfg.wc' not in pack_file and 'CmdSeq.wc' not in pack_file and 'Thumbs.db' not in pack_file \
				and ext != 'ztmp' and ext != 'nod' and ext != 'nrp': # nobody wants these
				log_file_action(pack_file, LOG_BIT_EXTRA, True)
				extra_content.append(fixed_path[0])
			
	content = list(set(content)) # remove duplicates

	new_files = []
	
	# generate res files
	content_normalized = [c.lower().replace('\\', '/') for c in content]
	content_normalized_but_not_lowercased = [c.replace('\\', '/') for c in content]
	bad_res_files = [] # res files with bad caps
	map_json['missing_files'] = set()
	bsps = [x.split(os.sep)[-1].replace(".bsp", "").replace(".BSP", "") for x in find_files(map_repack_dir + "/maps", "*.bsp")]
	res_content = []
	for bsp in sorted(bsps):
		print("Generating res file for %s..." % bsp)
		
		res_file = "maps/%s.res" % bsp
		
		# remove .res files with bad capitalization
		res_key = res_file.lower()
		if res_key in content_normalized and res_key in content_map:
			actual_res_name = os.path.basename(content_map[res_key])
			if actual_res_name != os.path.basename(res_file):
				content = [c for c in content if os.path.basename(c.replace('\\', '/')) != actual_res_name]
				content_normalized = [c.lower().replace('\\', '/') for c in content]
				log_file_action(content_map[res_key], LOG_NOT_NEEDED)
		
		res_content += gen_res_file(map_repack_dir, bsp)			
		
		if os.path.exists(os.path.join(map_repack_dir, res_file)):
			if res_file.lower() not in content_normalized:
				content.append(res_file)
				new_files.append(res_file)
		else:
			if res_file.lower() in content_normalized:
				content = [c for c in content if c.lower().replace('\\', '/') != res_file.lower()]
				key = res_file.lower().replace('/', os.sep)
				if key in content_map:
					log_file_action(content_map[key], LOG_NOT_NEEDED)
				
		# Add server-only files to list so they aren't removed from the archive
		if os.path.exists(os.path.join(map_repack_dir, res_file + '2')):
			with open(os.path.join(map_repack_dir, res_file + '2')) as f:
				server_files = f.read().splitlines()
			res_content += server_files
	map_json['missing'] = len(map_json['missing_files'])
	map_json.pop('missing_files', None)

	# remove files not included in the .res or .res2 files
	res_content = [c.replace('\\', '/') for c in res_content]
	res_content_lower = [c.lower().replace('\\', '/') for c in res_content]
	new_content = []
	for c in content: 
	
		is_readme = False
		'''
		is_readme = False
		fname = os.path.basename(c.lower())
		if ('readme' in fname or 'credit' in fname) and '.txt' in fname:
			is_readme = True
		'''
		
		if c.lower().replace('\\', '/') in res_content_lower or (include_readmes and is_readme):
			new_content.append(c)
		elif c.lower() in content_map:
			
			log_file_action(content_map[c.lower()], LOG_NOT_NEEDED)
			ext = c.split('.')[-1].lower()
			if ext != 'res':
				extra_content.append(c)
				log_file_action(content_map[c.lower()], LOG_BIT_EXTRA, True)
				
	# Add readmes
	if include_readmes:
		for bsp in bsps:
			readme_file = "maps/" + bsp + "_readme.txt"
			old_readme_file = "maps/" + bsp + ".txt"
			
			if os.path.isfile(os.path.join(map_repack_dir, readme_file)):
				extra_content.remove(readme_file)
				new_content.append(readme_file)
				log_file_action(content_map[readme_file.lower()], 0, reset_flags=True)
			else:
				if not os.path.exists(os.path.join(map_repack_dir, old_readme_file)):
					for file in os.listdir(os.path.join(map_repack_dir, "maps")):
						if (len(bsps) == 1 or bsp.lower() in file.lower()) and "readme" in file.lower():
							old_readme_file = "maps/" + file
				if os.path.isfile(os.path.join(map_repack_dir, old_readme_file)) and old_readme_file.lower() not in res_content_lower:
					os.rename(os.path.join(map_repack_dir, old_readme_file), os.path.join(map_repack_dir, readme_file))
					if old_readme_file in extra_content: extra_content.remove(old_readme_file)
					new_content.append(readme_file)
					if old_readme_file.lower() in content_map:
						log_file_action(content_map[old_readme_file.lower()], LOG_RENAMED, reset_flags=True)
	
	# Add files that were recovered
	lower_content = [x.lower().replace('\\','/') for x in new_content]
	recovered_files = []
	for c in res_content:
		if c.lower() not in lower_content and c.lower():
			new_content.append(c)
			recovered_files.append(c)
			
	# add extras to a special subfolder
	if include_extras:
		old_dir = os.getcwd()
		os.chdir(map_repack_dir)
		for c in extra_content:
			new_path = os.path.join("extras", c)
			os.makedirs(os.path.dirname(new_path), exist_ok=True)
			shutil.move(c, new_path)
			new_content.append(new_path)
		os.chdir(old_dir)
	
	content = new_content
	
	content = list(set(content)) # remove duplicates
	list_file = os.path.join(map_repack_dir, 'repack_file_list.txt')
	f = open(list_file, 'wb')
	for c in content:
		if not os.path.exists(c):
			c = fix_asset_capitalization(c)
		f.write(('%s\r\n' % c).encode("utf-8"))
	f.close()
	
	# check for scripts
	for c in content:
		if c.startswith('scripts/') and c.lower().endswith('.as'):
			map_json['scripted'] = True
	
	map_json['new_files'] = list_to_tree( [x.replace('\\', '/') for x in content] )
	for file in new_files:
		log_file_action(file, LOG_ADDED, new_files=True)
	for file in recovered_files:
		log_file_action(file, LOG_RECOVERED, new_files=True)
	
	# create 7zip archive for map content
	out_name = '%s.%s' % (safe_mapname, zip_type)
	out_path = os.path.join(map_download_dir, out_name)
	if os.path.isfile(out_path):
		os.remove(out_path)
	
	os.chdir(map_repack_dir)
	program_path = os.path.join(work_dir,'7za.exe') if platform.system() == "Windows" else "7za"
	try:
		print("Compressing %s..." % out_name)
		with open(os.devnull, 'w') as devnull:
			args = [program_path, 'a', zip_level, '-t%s' % zip_type, '-mmt', '-scsUTF-8', '../%s' % out_name, '@repack_file_list.txt']
			zip_stdout=None if debug_zip else devnull
			subprocess.check_call(args, stdout=zip_stdout)
	except Exception as e:
		print(e)
	os.chdir(work_dir)
	
	# create 7zip archive for extra content
	map_json['extras'] = len(extra_content)
	if not include_extras:
		extra_content = list(set(extra_content))
		if len(extra_content) > 0:
			extra_list_file = os.path.join(map_repack_dir, 'extra_file_list.txt')
			f = open(extra_list_file, 'wb')
			for c in extra_content:
				if not os.path.exists(c):
					c = get_asset_capitalization(c)
				f.write(('%s\r\n' % c).encode("utf-8"))
			f.close()
			
			out_name_extra = '%s_extras.%s' % (safe_mapname, zip_type)
			out_path_extra = os.path.join(map_download_dir, out_name_extra)
			if os.path.isfile(out_path_extra):
				os.remove(out_path_extra)
			
			os.chdir(map_repack_dir)
			program_path = os.path.join(work_dir,'7za.exe') if platform.system() == "Windows" else "7za"
			try:
				print("Compressing %s..." % out_name_extra)
				with open(os.devnull, 'w') as devnull:
					args = [program_path, 'a', zip_level, '-t%s' % zip_type, '-mmt', '-scsUTF-8', '../%s' % out_name_extra, '@extra_file_list.txt']
					zip_stdout=None if debug_zip else devnull
					subprocess.check_call(args, stdout=zip_stdout)
			except Exception as e:
				print(e)
			os.chdir(work_dir)
			
			map_json['extras_size'] = os.path.getsize(out_path_extra)
	else:
		map_json['extras_size'] = 0
	
	if not os.path.isfile(out_path):
		print("Repack failed!")
		if not debug_repack:
			shutil.rmtree(map_repack_dir)	
		return False
	
	# compute space saved
	new_size = os.path.getsize(out_path)
	
	space_saved = old_size - new_size
	
	map_json['old_ext'] = archive_path.split(".")[-1];
	map_json['old_size'] = old_size;
	map_json['new_size'] = new_size;
	
	if verbose:
		if space_saved >= 0:
			kb = int(space_saved / 1024)
			if kb > 0:
				print("Repack saved %s KB" % kb)
			else:
				print("Repack saved %s Bytes" % space_saved)
		else:
			kb = int(space_saved / -1024)
			print("Repack inflated size by %s KB." % kb)
	
	# cleanup
	if not debug_repack:
		shutil.rmtree(map_repack_dir)
		if archive_path != out_path:
			os.remove(archive_path)
	
	
	return no_issues

def base36(num):
	b36 = '';

	while num:
		b36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[int(num % 36)] + b36
		num = int(num / 36)
		
	return b36;
	
def extract_content_zip(idx, zip, out_path, total_zips=0, bigone_mode=False, allow_invalid=False):
	global pool_json
	global master_json
	
	has_any_scripts = False
	
	is_extra = '_extras.' in zip
	map_name = zip[:zip.rfind('.')]
	if is_extra:
		map_name = map_name[:map_name.rfind('_extras')]
	map_name = map_name.split(os.sep)[-1].lower()
	
	for key, value in master_json.items():
		if safe_map_name(key).lower() == map_name:
			map_name = key
			break
			
	if idx != -1:
		print("IDX: %s / %s, MAP: %s" % (idx, total_zips, map_name + (" (extras)" if is_extra else "")))
	else:
		print("Extracting pool content for: %s" % zip)
	
	pool_dir = bigone_dir if bigone_mode else map_pool_dir
	
	if os.path.exists(out_path):
		shutil.rmtree(out_path)
	os.makedirs(out_path)
	extract_archive(zip, out_path)
	pack_files = find_files(out_path, '*')
	conflicts = 0
	for p in pack_files:
		p = p.split(out_path)[-1][1:]
		ext = p.split(".")[-1]
		if ext.lower() == 'res' and not bigone_mode:
			continue
		fixed_path = fix_asset(p, out_path)
		if fixed_path[1] or allow_invalid:
			#print("Usable: %s" % p)
			p = fixed_path[0]
			if p.startswith('scripts/'):
				has_any_scripts = True
				
			target_path = os.path.join(pool_dir, p)
			src_path = os.path.join(out_path, p)
			if os.path.exists(target_path):
				if not filecmp.cmp(target_path, src_path):
					# files aren't the same
					conflicts = 1 if conflicts == 0 else 2
					src_time = os.path.getmtime(src_path)
					tar_time = os.path.getmtime(target_path)
					old_time = src_time if src_time > tar_time else tar_time
					old_name = p[:-(len(ext) + 1)] + '@' + base36(int(old_time / 60)) + '.' + ext
					old_path = os.path.join(pool_dir, old_name)
					
					if src_time < tar_time:
						if not os.path.exists(old_path) and not bigone_mode: 
							# old version of file not already in pool
							shutil.move(src_path, old_path)
						
						pool_json = log_file_src(pool_json, old_name, map_name, is_extra=is_extra, is_conflict=True)
						pool_json = log_file_src(pool_json, p, '', is_conflict=True) # Mark other as conflicted too
								
						print("Got older: %s" % old_name)
					else:
						if not os.path.exists(old_path): 
							# old version of file not already in pool
							if not bigone_mode:
								shutil.move(target_path, old_path)
							shutil.move(src_path, target_path)
						
						old_srcs = get_file_src(pool_json, p)
						pool_json = log_file_src(pool_json, p, map_name, True, is_extra=is_extra, is_conflict=True)
						for src in old_srcs['refs']:
							if len(src) == 0:
								continue
							old_is_extra = src[0] == '+'
							pool_json = log_file_src(pool_json, old_name, src[1:], is_extra=old_is_extra, is_conflict=True)
							
						print("Got newer: %s" % old_name)
					
						conflicts = 2
				else:
					# File already exists but is the same
					pool_json = log_file_src(pool_json, p, map_name, is_extra=is_extra)
			else:
				# new file
				
				target_dir = os.path.dirname(target_path)
				if not os.path.exists(target_dir):
					os.makedirs(target_dir)
				shutil.move(src_path, target_path)
				pool_json = log_file_src(pool_json, p, map_name, is_extra=is_extra)
		else:
			pass
			#print("Bad file: %s" % p)
		
	#if conflicts:
	#	os.system("pause")
	return has_any_scripts
	
def create_content_pool(bigone_mode=False, map_packs_only=False, bigone_extras=False):
	global pool_json
	global master_json
	global zip_type
	global blacklisted_bigone_maps
	global all_maps
	
	pool_dir = bigone_dir if bigone_mode else map_pool_dir
	
	total_no_dl = 0
	
	all_zips = []
	if map_packs_only:
		all_zips = [x for x in find_files(map_pack_cache_dir, '*.zip')]
	else:
		if bigone_mode:
			all_zips = []
			for map in all_maps:
				if bigone_extras:
					fname = os.path.join(map_download_dir, "%s_extras.%s" % (safe_map_name(map), zip_type))
				else:
					fname = os.path.join(map_download_dir, "%s.%s" % (safe_map_name(map), zip_type))
				if map in blacklisted_bigone_maps:
					print("Blacklisted map " + map)
					total_no_dl += 1
					continue
				if os.path.exists(fname):
					all_zips.append(fname)
				else:
					if 'default' in master_json[map] and master_json[map]['default']:
						total_no_dl += 1
						continue
					if 'failed' in master_json[map] and master_json[map]['failed']:
						total_no_dl += 1
						continue
					if bigone_extras and ('extras' not in master_json[map] or master_json[map]['extras'] == 0):
						continue
					print("Missing download for %s" % map)
			'''
			actual_zips = [x for x in find_files(map_download_dir, '*.%s' % zip_type) if len(x.split(os.sep)) == 2]
			for zip in actual_zips:
				if zip not in all_zips and '_extras.' not in zip:
					print("Map not in DB: %s" % zip)
			'''
		else:
			all_zips = [x for x in find_files(map_download_dir, '*.%s' % zip_type) if len(x.split(os.sep)) == 2]
		
	print("Prepare to extract %s maps! (%s total, but skipping %s maps)" % (len(all_zips), len(all_zips) + total_no_dl, total_no_dl))
		
	if bigone_mode:
		if os.path.exists(pool_dir):
			shutil.rmtree(pool_dir)
		
	if not os.path.exists(pool_dir):
		os.makedirs(pool_dir)
		
	#all_zips = all_zips[:2]
		
	unpack_dir = 'unpack'
	out_path = os.path.join(pool_dir, unpack_dir)
	
	# some zips will have bad stuff in them, but also usable content
	all_zips = sorted(all_zips[0:])
	total_zips = len(all_zips)
	for idx, zip in enumerate(all_zips):
		print("")
		if extract_content_zip(idx, zip, out_path, total_zips, bigone_mode=bigone_mode, allow_invalid=bigone_extras) and bigone_mode and not bigone_extras:
			# the map had scripts. Include the extras just in case the repacker deleted files it shouldn't have (no sure way to know this)
			extra_zip = zip.replace(".zip", "_extras.zip")
			if os.path.exists(extra_zip):
				extract_content_zip(idx, extra_zip, out_path, total_zips, bigone_mode=bigone_mode)
		
	if os.path.exists(out_path):
		shutil.rmtree(out_path)
		
	json_name = os.path.join(pool_dir,bigone_json_name) if bigone_mode else pool_json_name
	with open(json_name, 'w') as outfile:
		json.dump(pool_json, outfile)
		
	# Create the archive
	if bigone_mode:
		print("Prepare to make the biggest fucking archive ever")
		
		os.chdir(pool_dir)
		all_files = list(Path('.').glob('**/*.*'))
		
		for result in all_files:
			print("Result: %s" % result)
			
		list_file = os.path.join('bigone_file_list.txt')
			
		f = open(list_file, 'wb')
		for c in all_files:
			f.write(('%s\r\n' % c).encode("utf-8"))
		f.close()
		
		now = datetime.now()
		#out_name = 'scmapdb.zip'
		out_name = 'scmapdb.7z'
		if os.path.isfile(out_path):
			os.remove(out_path)
			
		program_path = os.path.join('..','7za.exe') if platform.system() == "Windows" else "7za"
		try:
			print("Compressing %s..." % out_name)
			with open(os.devnull, 'w') as devnull:
				#args = [program_path, 'a', '-mx1', '-tzip', '-mmt', '-scsUTF-8', '%s' % out_name, '@bigone_file_list.txt']
				args = [program_path, 'a', '-mx9', '-t7z', '-mmt=3', '-md=32m', '-scsUTF-8', '%s' % out_name, '@bigone_file_list.txt']
				subprocess.check_call(args)
		except Exception as e:
			print(e)
			raise Exception("Failed to create bigone archive!")
	
def remove_pool_references(map, dont_actually_remove=False):
	num_removed = [0]
	def remove_refs(tree, ref, path):
		global map_pool_dir
		
		for k, v in list(tree.items()):
			is_leaf = isinstance(v, dict) and 'refs' in v and isinstance(v['refs'], list)
			if is_leaf:
				if not dont_actually_remove:
					for idx, r in enumerate(v['refs']):
						if r[1:].lower() == ref.lower():
							del v['refs'][idx]
							num_removed[0] += 1
							break
							
				# Remove file from pool if this was the last reference
				if len(v['refs']) == 0 or len(v['refs']) == 1 and v['refs'][0] == '':
					if int(v['flags']) & 1 != 0:
						# file had conflicts, check if those are now cleared
						fname = k
						if k.find("@") > 0:
							fname = k[:k.find("@")] + k[k.rfind("."):]
							
						#print("DELETE KEY: %s SEARCH FOR: %s" % (k, fname))
						
						conflicts = []
						for k2, v2 in tree.items():
							f = k2
							if f.find("@") > 0:
								f = f[:f.find("@")] + f[f.rfind("."):]
							if f == fname and f != k:
								conflicts.append(k2)
						
						if len(conflicts) == 1:
							#print("Only 1 other file with this name. I guess it isn't conflicted anymore!")
							c = conflicts[0]
							conflict = tree[c]
							if c.find("@") > 0:
								tree[fname] = tree[c].copy()
								del tree[c]
								tree[fname]['flags'] = int(tree[fname]['flags']) & ~1
								
								old_name = os.path.join(map_pool_dir, path + '/' + c if len(path) else c )
								new_name = os.path.join(map_pool_dir, path + '/' + fname if len(path) else fname )
								shutil.move(old_name, new_name)
								print("Renamed %s to %s" % (c, fname))
								
							if c != k:
								del tree[k]
						else:
							del tree[k]
					else:
						del tree[k]
			else:
				remove_refs(v, ref, path + '/' + k if len(path) else k)
	remove_refs(pool_json, map, '')
	return num_removed[0]
	
def remove_unreferenced_pool_files():
	global pool_json
	global all_maps
	
	alt_paths = {}	
	
	def remove_inner(node):
		for k, v in list(node.items()):
			is_leaf = isinstance(v, dict) and 'refs' in v and isinstance(v['refs'], list)
			if is_leaf:
				newrefs = []
				for ref in v['refs']:
					if ref[1:] in all_maps:
						newrefs.append(ref)
				v['refs'] = newrefs
				if len(v['refs']) == 0 or len(v['refs']) == 1 and v['refs'][0] == '':
					del node[k]
					print("no refs: " + k)
			else:
				remove_inner(node[k])	
				
	# Get list of files that would have the same path as 'path' if case sensitivity was ignored (Windows)
	def mark_case_insensitive_conflicts(tree, path, conflicts={}):							
		for k, v in list(tree.items()):
			is_leaf = isinstance(v, dict) and 'refs' in v and isinstance(v['refs'], list)
			full_path = (path + '/' + k if len(path) else k).lower()
			if is_leaf:
				if full_path not in conflicts:
					conflicts[full_path] = 1
				else:
					conflicts[full_path] += 1
					#tree[k]['flags'] = int(tree[k]['flags']) | 1
			else:
				conflicts = mark_case_insensitive_conflicts(tree[k], full_path, conflicts)
				
		if path == '':
			# at root level			
			def mark_case_insensitive_conflicts_inner(tree, parts):
				for k, v in list(tree.items()):
					if k.lower() == parts[0]:
						is_leaf = isinstance(v, dict) and 'refs' in v and isinstance(v['refs'], list)
						if is_leaf:
							tree[k]['flags'] = int(tree[k]['flags']) | 1
						else:
							mark_case_insensitive_conflicts_inner(tree[k], parts[1:])
			
			for k, v in list(conflicts.items()):
				if v > 1:
					mark_case_insensitive_conflicts_inner(pool_json, k.split('/'))
					#print("OMG CONFLICT CASE: %s %s" % (k, v))
		else:	
			return conflicts
				
	def resolve_conflicts(tree, path):
		for k, v in list(tree.items()):
			is_leaf = isinstance(v, dict) and 'refs' in v and isinstance(v['refs'], list)
			if is_leaf:
				full_path = path + '/' + k if len(path) else k
				#mark_case_insensitive_conflicts(pool_json, pool_json.items(), full_path.split('/'))
				
				if (int(tree[k]['flags']) & 1) != 0:
					conflicts = []
					fname = k
					
					if k.find("@") > 0:
						fname = k[:k.find("@")] + k[k.rfind("."):]
					
					for k2, v2 in tree.items():
						f = k2
						if f.find("@") > 0:
							f = f[:f.find("@")] + f[f.rfind("."):]
						if f == fname:
							conflicts.append(k2)
					
					if len(conflicts) != 1:
						for c in conflicts:
							if (int(tree[c]['flags']) & 1) == 0:
								tree[c]['flags'] = int(tree[c]['flags']) | 1
								print("ACTUALLY CONFLICTED %s %s " % (fname, len(conflicts)))
							
					if len(conflicts) == 1:
						c = conflicts[0]
						conflict = tree[c]
						
						# shouldn't be conlicted anymore
						if c.find("@") > 0:
							old_name = os.path.join(map_pool_dir, path + '/' + c if len(path) else c )
							new_name = os.path.join(map_pool_dir, path + '/' + fname if len(path) else fname )
							if os.path.exists(new_name):
								backup_dir = os.path.join(old_pool_dir, path)
								backup_path = os.path.join(old_pool_dir, path + '/' + c if len(path) else fname )
								if not os.path.exists(backup_dir):
									os.makedirs(backup_dir)
								shutil.move(new_name, backup_path)
								print("Archived current version of " + fname)
							if os.path.exists(old_name):
								shutil.move(old_name, new_name)
								print("Renamed %s to %s" % (c, fname))	
							else:
								print("Rename %s to %s FAILED! (file didn't exist)" % (c, fname))	
							
							
							tree[fname] = tree[c].copy()
							del tree[c]
						tree[fname]['flags'] = int(tree[fname]['flags']) & ~1
						#print("Removed conflict flag for " + fname)
			else:
				resolve_conflicts(tree[k], path + '/' + k if len(path) else k)
				
	print("Removing unreferenced files...")
	remove_inner(pool_json)
	print("Resolving conflicted files that have a single reference...")
	resolve_conflicts(pool_json, '')
	print("Marking case insensitive conflicts...")
	mark_case_insensitive_conflicts(pool_json, '')
	print("Done handling conflicts")
	
# Check recent activity for new stuff. If everything there is new, then we have to go through and check all 1000 maps..
def update_maps_quick():
	global master_json
	
	print("Checking %s/repacker:map-edits\n" % domain_name)
	sys.stdout.flush()
	
	#f = urllib.request.urlopen("http://scmapdb.com") # Update: Special change list for repacker added!
	mdom = html.fromstring(read_url_safe("%s/repacker:map-edits" % domain_name))

	#recents = mdom.cssselect('#wiki-tab-0-0 .list-pages-item') # Update: Recent activity was replaced with "Recent edits"
	#recents = mdom.cssselect('.changes-list-item') 
	recents = mdom.cssselect('.actualcontent .list-pages-box .list-pages-item')
	
	remembered_some_maps = False
	
	visited = []
	
	idx = 0
	total = len(recents)
	had_any_updates = False
	for recent in recents:
		#map = recent.cssselect('.lister-item-title a')[0].attrib['href'].split("/map:")[-1]
		idx += 1
		'''
		href = recent.cssselect('.title a')[0].attrib['href']
		if '/map:' not in href:
			continue
		map = href.split("/map:")[-1]
		if map.lower() in visited:
			continue
		visited.append(map.lower())
		'''
		
		href = recent.cssselect('a')[0].attrib['href']
		map = href.split("/map:")[-1]
		has_new_revision = False
		new_rev = int(recent.cssselect('table tr:nth-child(3) > td:nth-child(2)')[0].text_content())
		has_new_revision = map not in master_json or int(master_json[map]['rev']) < new_rev	
		#print("rev: %s %s %s " % (map, int(master_json[map]['rev']), new_rev))
		needs_update = has_new_revision and is_map_outdated(map)
		
		if needs_update:
			mapurl = read_url_safe("%s%s" % (domain_name, href), returnUrlInsteadOfPageData=True)
			redirect_map = mapurl.split("/map:")[-1] 
			if redirect_map != map:
				print("%s redirects to %s" % (map, redirect_map))
				map = redirect_map
				has_new_revision = map not in master_json or int(master_json[map]['rev']) < new_rev
				needs_update = has_new_revision and is_map_outdated(map)
		
		if needs_update:
			print("")
			if map not in master_json and map not in all_maps:
				print("NEW MAP: %s" % map)
				all_maps.append(map)
				f = open('maplist.txt', 'wb')
				for c in sorted(all_maps):
					f.write(('%s\r\n' % c).encode("utf-8"))
				f.close()
			else:
				print("Updating map: %s" % map)
			update_map(map)
			print("")
			had_any_updates = True
		else:
			#print("%s / %s: %s" % (idx, total, map.ljust(50)), end="\r")
			remembered_some_maps = True
	
	if not had_any_updates:
		print("Everything is up-to-date.")
	else:
		print("")
	
	sys.stdout.flush()
	
	# Check map count
	mdom = html.fromstring(read_url_safe(domain_name))
	
	map_count = mdom.cssselect('.countbox table > tr:nth-child(1) > td.countnum p')
	if len(map_count):
		map_count = int(map_count[0].text_content())
	else:
		print("Uh oh couldn't parse map count from landing page")
		map_count = 0
	
	correct_number_of_maps = map_count == len(master_json) and map_count == len(all_maps)
	if not correct_number_of_maps:
		print("Map count mismatch (actual=%s, repacked=%s, maplist=%s)" % (map_count, len(master_json), len(all_maps)))
	
	return (remembered_some_maps, correct_number_of_maps, map_count)
	
def update_map(map, repack_only=False):
	global master_json
	global map_json
	global pool_json
	global zip_type
	
	safe_name = safe_map_name(map)
	zip = os.path.join(map_download_dir, "%s.%s" % (safe_name, zip_type))
	extra_zip = os.path.join(map_download_dir, "%s_extras.%s" % (safe_name, zip_type))
	
	# delete zips if they alreadu exist (repack or error)
	if (os.path.isfile(zip)):
		os.remove(zip)
	if (os.path.isfile(extra_zip)):
		os.remove(extra_zip)
	
	map_json = {}
	download_map(map, skip_cache=True)
	master_json[map] = map_json
	export_map_detail(map)
	
	if not repack_only:
		with open(master_json_name, 'w') as outfile:
			json.dump(master_json, outfile)
	
	# Only update content pool when downloading new stuff (repacks only reuse old content)
	if not repack_only:
		# Remove all references to this map in the pool file
		num_refs_removed = remove_pool_references(map)
		print("Removed %s pool file references" % num_refs_removed)

		unpack_dir = 'unpack'
		out_path = os.path.join(map_pool_dir, unpack_dir)
	
		if (os.path.isfile(zip)):
			extract_content_zip(-1, zip, out_path)
		if (os.path.isfile(extra_zip)):
			extract_content_zip(-1, extra_zip, out_path)
		
		with open(pool_json_name, 'w') as outfile:
			json.dump(pool_json, outfile)
	
def update_all_maps(force_all=False, repack_only=False):
	global master_json
	global all_maps
	global pool_json
	global force_zip_cache
	
	if not force_all and not repack_only:
		remembered_some_maps, correct_number_of_maps, correct_map_count = update_maps_quick()
		if remembered_some_maps:
			print("")
			print("The recent map edit list had maps we saw in the last update.")
			print("We can exit early in this case :>")
			
			if not correct_number_of_maps:
				print("")
				print("Uh oh the map count on SCMapDB doesn't match the maplist/json. Can't exit yet.")
				if correct_map_count != len(all_maps):
					print("Rewriting map list due to mismatched map count.")
					new_maps = update_map_list()
					for map in new_maps:
						print("")
						update_map(map)
					
				if len(all_maps) != len(master_json):
					print("Checking for extra/missing maps in the repack json...")
					for map in list(master_json.keys()):
						if map not in all_maps:
							delete_map_from_json(map)
					if correct_map_count == len(all_maps) and correct_map_count > len(master_json):
						num_to_update = correct_map_count - len(master_json)
						print("The repack json is missing %s maps. Updating now." % num_to_update)
						first_update = True
						for idx, map in enumerate(all_maps[0:]):
							if map in master_json:
								if not first_update:
									print('')
									print("%s is already in the repack json. Skipping." % map)
								continue
							else:
								if first_update:
									if idx > 0:
										print("Skipped %s maps that were already updated" % idx)
									first_update = False
								print('')
								print("IDX: %s / %s, MAP: %s"  % (idx, len(all_maps), map))
							update_map(map)
			else:
				print("Number of maps matches data.json (%s)" % (len(all_maps)))
			
			return
		else:
			print("")
			print("---------------------------------- ATTENTION ----------------------------------")
			print(("The recent activity feed had nothing familiar in it. In order to complete the \n" + 
				  "update, all maps will need to be checked. This will generate %s page requests, \n" +
				  "which isn't very nice for their site. This is going to take a long time!\n") % len(all_maps))
			print("Try to run updates more frequently so that the activity feed has stuff in it \n" +
				  "that the updater saw last time. If everything is new, then the updater won't\n"
				  "know if it missed something.\n")
			os.system("pause")
			
	if not repack_only:
		update_map_list()
	
	print("")
	if repack_only:
		print("Repacking %s maps..." % len(all_maps))
		force_zip_cache = True # don't download updated zips
	else:
		print("Checking %s maps for updates..." % len(all_maps))
		
	num_updates = 0
	for idx, map in enumerate(all_maps[0:]):
		print('')
		print("IDX: %s / %s, MAP: %s"  % (idx, len(all_maps), map))
		
		needs_update = repack_only or is_map_outdated(map)
		
		if needs_update:
			if not repack_only:
				print("Update required!")
			update_map(map, repack_only)
			num_updates += 1
	
	if not repack_only:
		print("%s of %s needed updates" % (num_updates, len(all_maps)))
	else:
		# only update at the end to save time
		with open(master_json_name, 'w') as outfile:
			json.dump(master_json, outfile)
	
def diff_trees(new, old, path, output, desc):
	root = new
	for part in path:
		root = root[part]
	
	for key, value in root.items():
		if type(root[key]) is int:
			otherRoot = old
			exists = True
			for part in path:
				if part in otherRoot:
					otherRoot = otherRoot[part]
				else:
					exists = False
					break
			exists = exists and key in otherRoot
			if not exists:
				file = ''
				for part in path:
					file += part + '/'
				file += key
				output.append("%s %s" % (desc, file))
				
		else:
			temp = path[:] # create a copy
			temp.append(key)
			output = diff_trees(new, old, temp, output, desc)
			
	return output
	
def diff_jsons(new_json_name, old_json_name):
	if os.path.isfile(old_json_name):
		print("Loading %s..." % old_json_name)
		with open(old_json_name) as f:
			json_dat = f.read()
		old_master_json = json.loads(json_dat, object_pairs_hook=collections.OrderedDict)
		
	if os.path.isfile(new_json_name):
		print("Loading %s..." % new_json_name)
		with open(new_json_name) as f:
			json_dat = f.read()
		new_master_json = json.loads(json_dat, object_pairs_hook=collections.OrderedDict)
		
	print("Preparing to diff %s and %s" % (new_json_name, old_json_name));
	for key, value in new_master_json.items():
		if key in old_master_json:
			new_dat = new_master_json[key]
			old_dat = old_master_json[key]
			old_missing = old_dat['missing'] if 'missing' in old_dat else 0
			new_missing = new_dat['missing'] if 'missing' in new_dat else 0
			
			output = []
			if old_missing != new_missing:
				if new_missing < old_missing:
					line = "Recovered %s files" % (old_missing-new_missing)
				else:
					line = "Missing %s more files" % (new_missing-old_missing)
				output.append(line)
				
			if 'new_files' in new_dat and 'new_files' in old_dat:
				diff_trees(new_dat['new_files'], old_dat['new_files'], [], output, '+ ')			
				diff_trees(old_dat['new_files'], new_dat['new_files'], [], output, '- ')			
			
			if output:
				print("\n%s" % new_dat['title'])
				for line in output:
					print("\t%s" % line)
		else:
			print("New map: %s" % key);
	
def export_map_detail(mapKey):
	global master_json
	value = master_json[mapKey]
	
	if 'resguy_log' not in value:
		print("Skipping detail export due to missing resguy_log key")
		return
		
	print("Exporting map detail")
	
	log_path = os.path.join(logs_dir, safe_map_name(mapKey) + ".json")
	detail_json = {}
	detail_json['resguy_log'] = value['resguy_log'] if 'resguy_log' in value else None
	detail_json['old_files'] = value['old_files'] if 'old_files' in value else None
	detail_json['new_files'] = value['new_files'] if 'new_files' in value else None
	detail_json['res_diff'] = value['res_diff'] if 'res_diff' in value else None
	detail_json['rating'] = value['rating'] if 'rating' in value else None
	detail_json['votes'] = value['votes'] if 'votes' in value else None
	detail_json['scrape_date'] = value['scrape_date'] if 'scrape_date' in value else None
	detail_json['release_date'] = value['release_date'] if 'release_date' in value else None
	
	if 'extras_size' in value:
		detail_json['extras_size'] = value['extras_size']
		del value['extras_size']
	if 'old_size' in value:
		detail_json['old_size'] = value['old_size']
		del value['old_size']
	if 'new_size' in value:
		detail_json['new_size'] = value['new_size']
		del value['new_size']
	if 'old_ext' in value:
		detail_json['old_ext'] = value['old_ext']
		del value['old_ext']
	
	with open(log_path, 'w') as outfile:
		json.dump(detail_json, outfile)
	
	num_moves = 0
	num_adds = 0
	num_rec = 0
	num_deletes = 0
	def get_op_counts(tree):
		nonlocal num_moves
		nonlocal num_adds
		nonlocal num_rec
		nonlocal num_deletes
		
		for key, value in tree.items():
			if type(tree[key]) is int: # leaf node
				action = int(tree[key]) & 255
				flags = int(tree[key]) &~255
				
				if action == 1 or action == 10:
					num_moves += 1
				elif action == 2 or action == 9:
					if action == 2:
						num_adds += 1
					if action == 9:
						num_rec += 1
				elif action != 0:
					num_deletes += 1
			else:
				get_op_counts(tree[key])
	
	num_res_rem = 0
	num_res_add = 0
	def get_op_counts_res(res_diff):
		nonlocal num_res_rem
		nonlocal num_res_add
		
		for key, list in res_diff.items():
			for idx, path in enumerate(list):
				if len(path) == 0:
					continue

				path = path[1:]
				if path == '-':
					num_res_rem += 1;
				else:
					num_res_add += 1;
	
	get_op_counts(value['old_files'])
	get_op_counts(value['new_files'])
	get_op_counts_res(value['res_diff'])
	
	value['num_adds'] = num_adds
	value['num_moves'] = num_moves
	value['num_resops'] = num_res_add + num_res_rem
	value['num_recovered'] = num_rec
	value['num_deleted'] = num_deletes
	if 'new_files' not in value or not value['new_files']:
		value['no_maps'] = True
	
	del value['resguy_log']
	del value['old_files']
	del value['new_files']
	del value['res_diff']
	del value['rating']
	del value['votes']
	del value['scrape_date']
	del value['release_date']

def read_url_safe(url, returnUrlInsteadOfPageData=False):
	connection_attempts = 5 # connection attempts to make before giving up
	connection_backoff = [0, 15, 30, 60, 60] # seconds to wait after each attempt
	
	for attempt in range(0, connection_attempts):
		waitTime = connection_backoff[attempt]
		if waitTime > 0:
			print("Waiting %s seconds" % waitTime)
			time.sleep(waitTime)
			print("Opening url again")
		try:
			f = urllib.request.urlopen(url, timeout=60)
			if returnUrlInsteadOfPageData:
				return f.geturl()
			data = f.read()
			f.close()
			return data
		except urllib.error.URLError as e:
			reason = e.reason if hasattr(e, 'reason') else '???'
			print("Failed to open url due to %s (attempt %s of %s)" % (reason, attempt+1, connection_attempts))
		except http.client.IncompleteRead as e:
			print("Failed to open url due to IncompleteRead (attempt %s of %s)" % (attempt+1, connection_attempts))
		except socket.timeout as e:
			print("Failed to open url due to timeout (attempt %s of %s)" % (attempt+1, connection_attempts))
		
	print("Failed to connect to SCMapDB. Aborting.")
	clean_exit()
	
def download_file_safe(url, file_name):
	connection_attempts = 20 # connection attempts to make before giving up
	connection_backoff = [0, 1, 2, 5, 10, 20, 30, 40, 50, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60] # seconds to wait after each attempt
	

	requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

	for attempt in range(0, connection_attempts):
		waitTime = connection_backoff[attempt]
		if waitTime > 0:
			print("Waiting %s seconds" % waitTime)
			time.sleep(waitTime)
			print("Downloading again")
		try:
			with requests.get(url, timeout=60, stream=True, verify=False) as r:
				r.raise_for_status() # throw on 404s
				with open(file_name, 'wb') as fh:
					# Walk through the request response in chunks of 120kb (2kb/s for 60 second timeout)
					for chunk in r.iter_content(1024 * 120):
						fh.write(chunk)
			
			if not validate_archive(file_name):
				# really rare for a corrupted acrchive to be uploaded, so probably a bad download or a 404 page.
				print("Downloaded file is corrupted or incomplete (attempt %s of %s)" % (attempt+1, connection_attempts))
				continue
			return True
		except requests.Timeout as e:
			print("Timeout downloading file (attempt %s of %s)" % (attempt+1, connection_attempts))
		except requests.exceptions.ConnectionError as e:
			if 'Connection refused' in str(e):
				# server's fault, not ours (most likely).
				raise Exception("Connection refused")
			print("ERROR IS: %s" % str(e))
			print("ConnectionError downloading file (attempt %s of %s)" % (attempt+1, connection_attempts))

	print("Failed to download file. Aborting.")
	clean_exit()

def load_the_big_guys():
	global master_json
	global pool_json
	
	# might take a while, this data really shouldn't be all in one file... oh well
	if os.path.isfile(master_json_name):
		print("Loading %s..." % master_json_name)
		with open(master_json_name) as f:
			json_dat = f.read()
		master_json = json.loads(json_dat, object_pairs_hook=collections.OrderedDict)
	
	sys.stdout.flush()
	
	pool_json = collections.OrderedDict({})
	if os.path.isfile(pool_json_name):
		print("Loading %s..." % pool_json_name)
		with open(pool_json_name) as f:
			json_dat = f.read()
		pool_json = json.loads(json_dat, object_pairs_hook=collections.OrderedDict)
		
	sys.stdout.flush()
	
def clean_exit():
	global in_progress_name
	
	lock_path = os.path.join(work_dir, in_progress_name)
	if os.path.isfile(lock_path):
		os.remove(lock_path)
	else:
		print("progress lock file not found: %s" % lock_path)
	sys.exit()
	
args = sys.argv[1:]
	
if len(args) < 1 or args[0].lower() == 'help':
	print("\nUsage:")
	print("sudo python3 scmapdb.py [command]\n")
	
	print("Available commands:")
	print("update - check for map edits and update maps as needed")
	print("update_full - force all maps to be checked for updates")
	print("repack_all - force all maps to be repacked using the current cache")
	print("repack [map] - Repack a map using the cached archive")
	print("remove [map] - Remove map from data.json and pool.json")
	print("update_one [map] - force a map to be redownloaded and repacked")
	print("pool - creates the content pool from the downloaded map cache")
	print("pool_packs - adds map pack content to the pool")
	print("bigone - creates the content pool without any extras or conflicted files")
	print("cache - refreshes the page and thumbnail caches")
	print("cache_one [map] - refreshes the page and thumbnail cache for a specific map")
	print("")
	print("First-time usage:")
	print("1. 'update'")
	print("2. 'pool_packs' (add map packs to content pool)")
	print("3. 'repack_all' (now that the pool is full, repack everything to recover missing files)")
	print("4. 'update' on loop forever. Do 'repack_all' occaisionally to fix missing files")
	print("")
	print("'ulimit -n' should be at least 4096 until the leaking file handle bug is fixed")
	
	sys.exit()
	
if os.path.isfile(in_progress_name):
	age = (time.time() - os.path.getmtime(in_progress_name)) / (60*60)
	if age > 2:
		print("Ignoring update lock - file is over 2 hours old")
		os.remove(in_progress_name)
	else:
		print("Update in progress. Aborting.")
		sys.exit(1)
		
os.umask(0)
open(in_progress_name, "a").close()


	
if os.path.isfile(default_content_fname):
	with open(default_content_fname) as f:
		lines = f.read().splitlines()
	for idx, k in enumerate(lines):
		if len(k) and '[' not in k:
			default_content.append(k.lower())
		if "[DEFAULT TEXTURES]" in k:
			break
else:
	print(default_content_fname + " is missing. Use resguy to create it.")
	clean_exit()
	
if os.path.isfile(link_rules_fname):
	rules = []
	with open(link_rules_fname) as f:
		rules = f.read().splitlines()
	for rule in rules:
		if len(rule.strip()) < 3 or rule.strip()[0] == '#':
			continue
		mapname = rule[:rule.find("=")].strip()
		index = rule[rule.find("=")+1:].strip()
		link_rules[mapname] = int(index)
		#print("Got link rule: '%s' -> '%s'" % (mapname, index))
	
if os.path.isfile(link_json_name):
	with open(link_json_name) as f:
		json_dat = f.read()
	link_json = json.loads(json_dat)

if os.path.isfile(map_list_fname):
	with open(map_list_fname) as f:
		all_maps = f.read().splitlines()
			

if len(args) > 0:
	if args[0].lower() == 'diff':
		if len(args) > 2:
			diff_jsons(args[1], args[2])
		else:
			diff_jsons(master_json_name, master_json_name + '.old')
		clean_exit()
			
	load_the_big_guys()
	
	if args[0].lower() == 'fixperms':
		fix_file_perms('.')
		os.chmod('resguy', stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
		os.chmod('cmd.sh', stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
	if args[0].lower() == 'pool':
		create_content_pool()
	if args[0].lower() == 'pool_packs':
		print("Adding map pack content to pool")
		create_content_pool(map_packs_only=True)
	if args[0].lower() == 'bigone':
		create_content_pool(bigone_mode=True)		
	if args[0].lower() == 'cache_one':
		print("Refreshing page/thumbnail cache")
		if len(args) > 1:
			if args[1] in all_maps:
				print('')
				print("IDX: %s / %s, MAP: %s"  % (idx, len(all_maps), map))
				get_map_urls(args[1], skip_cache=True)
	if args[0].lower() == 'cache':
		for idx, map in enumerate(all_maps[0:]):
			print('')
			print("IDX: %s / %s, MAP: %s"  % (idx, len(all_maps), map))
			get_map_urls(map, skip_cache=True)
	if args[0].lower() == 'test':
		for idx, map in enumerate(all_maps[0:]):
			detail_json_name = logs_dir + '/' + safe_map_name(map) + '.json'
			detail_json = None
			rev = 0
			if os.path.exists(detail_json_name):
				with open(detail_json_name) as f:
					json_dat = f.read()
					detail_json = json.loads(json_dat, object_pairs_hook=collections.OrderedDict)
				if 'rev' in detail_json:
					print("LOAD REV %s for %s" % (detail_json['rev'], map))
					rev = detail_json['rev']
				else:
					print("NO REV FOR MAP %s" % map)
				
			master_json[map]['rev'] = rev
			
		with open(master_json_name, 'w') as outfile:
			json.dump(master_json, outfile)
			
	if args[0].lower() == 'repack':
		if len(args) > 1:
			if args[1] in master_json:
				force_zip_cache = True
				remove_pool_references(args[1], dont_actually_remove=False)
				download_map(args[1])
				master_json[args[1]] = map_json
				export_map_detail(args[1])
				
				unpack_dir = 'unpack'
				out_path = os.path.join(map_pool_dir, unpack_dir)
				zip = os.path.join(map_download_dir, "%s.%s" % (safe_map_name(args[1]), zip_type))
				zip_extra = os.path.join(map_download_dir, "%s_extras.%s" % (safe_map_name(args[1]), zip_type))
				if os.path.exists(zip):
					extract_content_zip(0, zip, out_path, 0)
				if os.path.exists(zip_extra):
					extract_content_zip(0, zip_extra, out_path, 0)
				if os.path.exists(out_path):
					shutil.rmtree(out_path)
				
				remove_unreferenced_pool_files()
				with open(master_json_name, 'w') as outfile:
					json.dump(master_json, outfile)
				with open(pool_json_name, 'w') as outfile:
					json.dump(pool_json, outfile)
			else:
				print("Map doesn't exist: %s" % args[1])
	if args[0].lower() == 'update_one':
		if len(args) > 1:
			if args[1] in all_maps:
				download_map(args[1], skip_cache=True)
				master_json[args[1]] = map_json
				export_map_detail(args[1])
				with open(master_json_name, 'w') as outfile:
					json.dump(master_json, outfile)
				with open(pool_json_name, 'w') as outfile:
					json.dump(pool_json, outfile)
		
	if args[0].lower() == 'update' or args[0].lower() == 'update_full' or args[0].lower() == 'repack_all':
		update_all_maps(args[0].lower() == 'update_full', args[0].lower() == 'repack_all')
		
		# resolve file conflicts
		print("")
		meps = sorted(all_maps[0:])
		len_meps = len(meps)
		remove_unreferenced_pool_files()
		with open(pool_json_name, 'w') as outfile:
			json.dump(pool_json, outfile)
			
		print("")
		print("Pushing changes to github")
		subprocess.run(['git', '--git-dir=.git_data', '--work-tree=.', 'add', logs_dir])
		subprocess.run(['git', '--git-dir=.git_data', '--work-tree=.', 'add', 'data.json'])
		subprocess.run(['git', '--git-dir=.git_data', '--work-tree=.', 'add', 'pool.json'])
		subprocess.run(['git', '--git-dir=.git_data', '--work-tree=.', 'add', 'maplist.txt'])
		subprocess.run(['git', '--git-dir=.git_data', '--work-tree=.', 'commit', '-m', 'automatic update'])
		subprocess.run(['git', '--git-dir=.git_data', '--work-tree=.', 'push'])
		
		print("")
		print("UPDATE COMPLETE")
		print("")
	if args[0].lower() == 'remove' and len(args) > 1:
		try:
			del master_json[args[1]]
		except:
			print("There is no map named '%s'" % args[1])
			clean_exit()
		remove_pool_references(args[1], dont_actually_remove=False)
		remove_unreferenced_pool_files()
		
		f = open('maplist.txt', 'wb')
		for c in all_maps:
			if c != args[1]:
				f.write(('%s\r\n' % c).encode("utf-8"))
		f.close()
		
		with open(master_json_name, 'w') as outfile:
			json.dump(master_json, outfile)
		with open(pool_json_name, 'w') as outfile:
			json.dump(pool_json, outfile)
		print("Deleted %s from data.json and removed pool references to it" % args[1])
	if args[0].lower() == 'fix_pool':
		meps = sorted(all_maps[0:])
		len_meps = len(meps)
		remove_unreferenced_pool_files()
		with open(pool_json_name, 'w') as outfile:
			json.dump(pool_json, outfile)
			
	clean_exit()
else:
	load_the_big_guys()

	
if use_cache:
	if not os.path.exists(map_cache_dir):
		os.makedirs(map_cache_dir)
	if not os.path.exists(map_pack_cache_dir):
		os.makedirs(map_pack_cache_dir)
	if not os.path.exists(page_cache_dir):
		os.makedirs(page_cache_dir)
	
if len(all_maps) == 0:
	update_map_list()
	
#repack_map('borg-cube', 'zip')
#download_map('biohazard')
#exit()

# Known bad maps:
# 43 is 404 page
# 127 has .bsp in models folder??? + uses uppercase folder name for standard folder
# 159 uses upper-case content folders
# 160 links to a 404 and a page with a link to the zip
# 189 probably needs a WAD file but need to analyze the BSP for that
# 195 + 222 is proof that some packs drop a .bsp in the root and call it a day
# 200 uses nested archives and overwrites default sounds >:|
# 208 points to a mappack and the wrong bsp names are given
# 357 uses 'sounds' instead of 'sound'
# 401 uses .asp for audio?? Does that even work? (also check .au)
# 457 needs a subfolder in sound but you'd only know that after seeing the Resguy log
# 540 uses a 'valve' folder and 'svencoop' :?
# 556 uses 'sounds' folder and tries to overwrite materials.txt
# 634 uses 'cue' files (do those even work?)
# 662 overwrites all models. This should just be fixed to use GMR
# 819 uses uppercase for bsp and lowercase for cfg
# 849 puts a sound in a model folder but might actually use it (need to analyze model sound events...)
# ETC II uses a bad sentence file path (but it looks like a false positive for resguy)
# garg football is missing ball model
# default content should only have the bare minimum to play SC, not any of the included maps
# some packs include ripent .ent files (like a changelog type thing I guess?)
# Lots have readmes.txt or credits.txt which aren't needed
# Maps that have "hotfixes" as separate downloads are not accounted for
# A lot of maps use "/sound/sentence(s).txt" but I think that just used to be a default value
# AMX .ini files are discarded
# what to do about player models that aren't used?
# I see "ambience/*waterfall3.wav" used in ambient_generics in some maps. It's invalid, but why is it so common? UPDATE: it's actually \*, which is valid...
# should mapname.txt files just be converted to mapname_motd.txt files? Or maybe post info in DB.
# Many maps include default content, but what if it's modified? Should it be kept but renamed or something?
# Uboa Rampage uses wrapper functions for precaching, so none of the weapon models are added

# More todo: Cleanup pool.json after update. Some conflicts will still show up even when they are fixed.

# Maps that need special attention:
# Afraid of Monsters - Duplicates almost everything in a Svencoop folder. Maybe some of this is a hotfix? Can't tell


start = time.time()

if log_to_file:
	class Logger(object):
		def __init__(self):
			self.terminal = sys.stdout
			self.log = open("scmapdb_log.txt", "a")

		def write(self, message):
			self.terminal.write(message)
			self.log.write(message) 
			self.terminal.flush()
			self.log.flush()
			
		def flush(self):
			self.terminal.flush()
			self.log.flush()
			
	sys.stdout = Logger() # Log all prints to file instead of console

for idx, map in enumerate(all_maps[0:]):
	print('')
	print("INDEX %s" % idx)
	map_json = {}
	special_case = download_map(map)
	if special_case:
		if False and os.path.isfile(os.path.join('downloads','%s.7z' % safe_map_name(map))):
			os.system('start downloads/%s.7z' % safe_map_name(map))
		#os.system('pause')
		
	master_json[map] = map_json
	with open(master_json_name, 'w') as outfile:
		json.dump(master_json, outfile)

end = time.time()
delta = int(end-start)
seconds = delta % 60
minutes = int(delta / 60)
print("Finished in %s minutes, %s seconds" % (minutes, seconds))

clean_exit()