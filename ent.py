import struct, os

def parse_keyvalue(line):
	if line.find("//") != -1:
		line = line[:line.find("//")]
		
	quotes = [idx for idx, c in enumerate(line) if c == '"']
	
	if len(quotes) < 4:
		return None
	
	key   = line[quotes[0]+1 : quotes[1]]
	value = line[quotes[2]+1 : quotes[3]]
	
	return (key, value)

def parse_ents(path, ent_text):
	ents = []

	lineNum = 0
	lastBracket = -1
	ent = None
	
	for line in ent_text.splitlines():
		lineNum += 1
		
		if len(line) < 1 or line[0] == '\n':
			continue
			
		if line[0] == '{':
			if lastBracket == 0:
				print("\n%s.bsp ent data (line %d): Unexpected '{'\n" % (path, lineNum));
				continue
			lastBracket = 0

			ent = {}

		elif line[0] == '}':
			if lastBracket == 1:
				print("\n%s.bsp ent data (line %d): Unexpected '}'\n" % (path, lineNum));
			lastBracket = 1

			if ent == None:
				continue

			ents.append(ent)
			ent = None

			# a new ent can start on the same line as the previous one ends
			if line.find("{") != -1:
				ent = {}
				lastBracket = 0

		elif lastBracket == 0 and ent != None: # currently defining an entity
			keyvalue = parse_keyvalue(line)
			if keyvalue:
				ent[keyvalue[0]] = keyvalue[1]
	
	return ents

def load_entities(bsp_path):
	with open(bsp_path, mode='rb') as f:
		bytes = f.read()
		version = struct.unpack("i", bytes[:4])
		
		offset = struct.unpack("i", bytes[4:4+4])[0]
		length = struct.unpack("i", bytes[8:8+4])[0]
		
		ent_text = bytes[offset:offset+length].decode("ascii", "ignore")
		
		return parse_ents(bsp_path, ent_text)
	
	print("\nFailed to open %s" % bsp_path)
	return None
	
def get_all_maps(maps_dir):
	all_maps = []
	
	for file in os.listdir(maps_dir):
		if not file.lower().endswith('.bsp'):
			continue
		if '@' in file:
			continue # ignore old/alternate versions of maps (w00tguy's scmapdb content pool)
			
		all_maps.append(file)
		
	return sorted(all_maps, key=lambda v: v.upper())



maps_dir = "./content_pool/maps"
LIFTABLE_FLAG = 1024

all_maps = get_all_maps(maps_dir)
broken_maps = []

skip_maps = []
with open("mapcycle.txt") as f:
	skip_maps = f.read().splitlines()

last_progress_str = ''
for idx, map_name in enumerate(all_maps):
	map_path = os.path.join(maps_dir, map_name)

	progress_str = "Progress: %s / %s  (%s)" % (idx, len(all_maps), map_name)
	padded_progress_str = progress_str
	if len(progress_str) < len(last_progress_str):
		padded_progress_str += ' '*(len(last_progress_str) - len(progress_str))
	last_progress_str = progress_str
	print(padded_progress_str, end='\r')
	
	if map_name.lower().replace(".bsp", "") in skip_maps:
		continue
	
	for ent in load_entities(map_path):
		if ('classname' in ent and ('monster_' in ent['classname'])) and 'spawnflags' in ent and int(ent['spawnflags']) & 1 != 0:
			broken_maps.append(map_name)
			print("\nMATCHED %s" % map_name)
			break
	
	'''
	for ent in load_entities(map_path):
		if 'classname' in ent and ent["classname"] == 'func_pushable':
			if 'spawnflags' in ent and int(ent['spawnflags']) & LIFTABLE_FLAG:
				broken_maps.append(map_name)
				print("\nOH NO %s" % map_name)
				break
	'''

print("\n\nResults:")
for map in broken_maps:
	print(map)