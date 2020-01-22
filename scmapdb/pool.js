var map_data = {};
var pool_data = {};
var file_tree;

function pretty_size(bytes) {
	if (bytes === undefined) {
		return "N/A";
	}
	if (bytes > 1024) {
		var kb = Math.ceil(bytes / 1024);
		if (kb > 1024) {
			var mb = Math.ceil(kb / 1024);
			return mb + " MB";
		}
		else
			return kb + " KB";
	}
	else
		return bytes + " Bytes";
}

var b36_vals = {
	'0': 0, '1': 1, '2': 2, '3': 3, 
	'4': 4, '5': 5, '6': 6, '7': 7, 
	'8': 8, '9': 9, 'A': 10, 'B': 11,
	'C': 12, 'D': 13, 'E': 14, 'F': 15,
	'G': 16, 'H': 17, 'I': 18, 'J': 19,
	'K': 20, 'L': 21, 'M': 22, 'N': 23,
	'O': 24, 'P': 25, 'Q': 26, 'R': 27,
	'S': 28, 'T': 29, 'U': 30, 'V': 31,
	'W': 32, 'X': 33, 'Y': 34, 'Z': 35
}

var all_files;
var num_files = 0;
var num_dirs = 0;
var filtering = false;

function write_tree(tree, path) {
	var out = '';
	
	if (!path) {
		path = '';
	}
	
	// sort files/folders within folder
	var sorted_keys = [];
	for (var key in tree) {
		if (tree.hasOwnProperty(key)) {
			var is_leaf = typeof tree[key] != 'object' || ('refs' in tree[key] && tree[key].refs.constructor === Array);
			
			sorted_keys[sorted_keys.length] = (is_leaf ? 'B' : 'A') + key;
		}
	}
	sorted_keys.sort(function(x, y) {
		var a = x.toLowerCase();
		var b = y.toLowerCase();
		if (a.indexOf("@") > 0) {
			var name = a.substr(0, a.indexOf("@"));
			name += a.substr(a.lastIndexOf("."));
			a = name;
		}
		if (b.indexOf("@") > 0) {
			var name = b.substr(0, b.indexOf("@"));
			name += b.substr(b.lastIndexOf("."));
			b = name;
		}
		return (a < b) ? -1 : (a > b) ? 1 : 0;
	});
	var sorted_keys2 = [];
	for (var key in sorted_keys) {
		sorted_keys2[key] = sorted_keys[key].substr(1);
	}
	
	for (var key in sorted_keys2) {
		key = sorted_keys2[key];
		var is_leaf = typeof tree[key] != 'object' || ('refs' in tree[key] && tree[key].refs.constructor === Array);
		if (is_leaf) {
			var c = '';
			out += '<div class="file" key="' + key + '" path="' + path + '"></div>';
			num_files += 1;
		} else {
			out += '<div class="folder closed smooth"><div class="arrow"><div class="border"></div></div>'
			out += '<span>' + key + "</span>"
			var subtree = write_tree(tree[key], path + (path.length ? "/" : "") + key);
			out += '<div class="content hidden2">' + subtree + '</div>';
			out += '</div>'
			num_dirs += 1;
		}
	}	
	
	return out;
}

function load_file_info(key, path) {
	var out = '';
	
	var tree = pool_data;
	
	var parts = path.split("/");
	for (var i = 0; i < parts.length; i++) {
		var part = parts[i];
		if (part.length) {
			tree = tree[part];
		}
	}

	var c = '';
	var fname = key;
	var hasConflicts = tree[key].flags & 1 != 0;
	if (hasConflicts) {
		c = 'conflict';
		if (fname.indexOf("@") > 0) {
			var ext = fname.substr(fname.lastIndexOf("."));
			fname = fname.substr(0, fname.lastIndexOf("@")) + ext;
		}
	}

	var date = new Date(tree[key].date*1000);
	date = date.getFullYear() + "/" + ('0'+(date.getMonth()+1)).slice(-2) + "/" + ('0'+date.getDate()).slice(-2);
	var details = "Path:\t" + path + (path.length ? "/" : "") + fname;
	details += "\nSize:\t" + pretty_size(tree[key].sz) + "    (" + tree[key].sz + " Bytes)";
	details += "\nDate:\t" + date;
	details += "\nCRC-32:\t" + tree[key].crc;
	
	out += '<div class="file" crc="' + tree[key].crc + '">' +'<span class="name ' + c + '" title="' + details + '">' + fname + '</span>'
	out += '<span class="ref-container">' 
	for (var k in tree[key].refs) {
		var map_name = tree[key].refs[k];
		var prefix = map_name[0];
		map_name = map_name.substr(1);
		var map_url = map_name;
		var refclass = prefix == '+' ? 'extra' : '';
		var suffix = prefix == '+' ? "\n\nFile included but not used in any map(s)" : "";
		var title = map_name;
		var author = '';
		var category = "map:";
		if (map_name in map_data && map_data[map_name]) {
			author = map_data[map_name]['author'];
			title = map_data[map_name].title + "\nby " + author + suffix;
			map_name = map_data[map_name].title;
		}
		else {
			// if it's not a map, it must be a map pack
			category = "mappack:";
		}
		out += '<a class="ref ' + refclass + '" target="_blank" href="http://scmapdb.com/' + category + map_url + '" title="' + title + '">' + map_name;
		out += '<span class="author hidden">' + author + '</span></a>';
	}
	out += '</span></div>'
	
	return $($.parseHTML(out));
}

function update_filter_hash() {
	var file_name = $('.name-filter').val().toLowerCase();
	var author_name = $('.author-filter').val().toLowerCase();
	var crc_name = $('.crc-filter').val().toLowerCase();
	var share_radio = parseInt( $('input[name="share-radio"]:checked').val() );
	var old_radio = parseInt( $('input[name="old-radio"]:checked').val() );
	var extra_radio = parseInt( $('input[name="extra-radio"]:checked').val() );	

	var maps_chk = $('.ftype[i="1"]').is(":checked") ? "1" : "0";
	var models_chk = $('.ftype[i="2"]').is(":checked") ? "1" : "0";
	var sprites_chk = $('.ftype[i="3"]').is(":checked") ? "1" : "0";
	var sounds_chk = $('.ftype[i="4"]').is(":checked") ? "1" : "0";
	var scripts_chk = $('.ftype[i="5"]').is(":checked") ? "1" : "0";
	var wads_chk = $('.ftype[i="6"]').is(":checked") ? "1" : "0";
	var text_chk = $('.ftype[i="7"]').is(":checked") ? "1" : "0";
	var bitmaps_chk = $('.ftype[i="8"]').is(":checked") ? "1" : "0";
	
	var hash = "#" + encodeURIComponent(file_name) + "&" + encodeURIComponent(author_name) + "&" + encodeURIComponent(crc_name);
	hash += "&" + share_radio + old_radio + extra_radio;
	hash += maps_chk + models_chk + sprites_chk + sounds_chk + scripts_chk + wads_chk + text_chk + bitmaps_chk;
	
	$('.share').attr("href", hash);
	window.location.hash = hash;
}

function load_hash_settings() {
	var hash = window.location.hash.substr(1);
	var filters = hash.split("&");
	
	if (filters.length <= 1) {
		return;
	}
	
	if (filters.length != 4 || filters[3].length != 11) {
		console.log("Invalid filter settings");
		return;
	}
	console.log("Applying URL filters");
	
	$('.name-filter').val(decodeURIComponent(filters[0]));
	$('.author-filter').val(decodeURIComponent(filters[1]));
	$('.crc-filter').val(decodeURIComponent(filters[2]));
	
	filters = filters[3];
	
	$('input[name="share-radio"][value="' + filters[0] + '"]').prop("checked", true);
	$('input[name="old-radio"][value="' + filters[1] + '"]').prop("checked", true);
	$('input[name="extra-radio"][value="' + filters[2] + '"]').prop("checked", true);
	
	$('.ftype[i="1"]').prop('checked', filters[3] != "0");
	$('.ftype[i="2"]').prop('checked', filters[4] != "0");
	$('.ftype[i="3"]').prop('checked', filters[5] != "0");
	$('.ftype[i="4"]').prop('checked', filters[6] != "0");
	$('.ftype[i="5"]').prop('checked', filters[7] != "0");
	$('.ftype[i="6"]').prop('checked', filters[8] != "0");
	$('.ftype[i="7"]').prop('checked', filters[9] != "0");
	$('.ftype[i="8"]').prop('checked', filters[10] != "0");
}

function apply_filters() {
	
	update_filter_hash();
	
	if (filtering) {
		filtering = false; // prompt filter loop to restart
		return;
	}
	filtering = true;
	var t0 = Date.now();
	var file_name = $('.name-filter').val().toLowerCase();
	var crc_name = $('.crc-filter').val().toLowerCase();
	var author_name = $('.author-filter').val().toLowerCase();
	var share_radio = parseInt( $('input[name="share-radio"]:checked').val() );
	var old_radio = parseInt( $('input[name="old-radio"]:checked').val() );
	var extra_radio = parseInt( $('input[name="extra-radio"]:checked').val() );	
	
	var valid_ftypes = [];
	$.each($('.ftype'), function(idx, chk) {
		chk = $(chk);
		if (chk.is(":checked")) {
			types = chk.attr("exts").split(" ");
			for (var i = 0; i < types.length; i++)
				valid_ftypes.push(types[i].toLowerCase());
		}
	});
	
	file_tree.detach();
	
	$('.loader, .loader-text').show();
	$('.load-action').text("Filtering");

	var filters_per_frame = 200;	
	var result_count = 0;
	var idx = 0;
	
	function filter_finished(result_count)
	{
		filtering = false;
		var result_count_with_folders = result_count;
		$.each(file_tree.find(".folder"), function(idx, dir) {
			dir = $(dir);
			var num_files = dir.find(".file:not(.exclude)").length;
			if (num_files > 0) {
				dir.removeClass("exclude");
				result_count_with_folders++;
			} else {
				dir.addClass("exclude");
			}
		});	

		$('.loader, .loader-text').hide();
		//file_tree.show();
		$('#file-tree').append(file_tree);
		$('.num-results').text(result_count + " Results");
		$('.num-results').removeClass("invisible");
		
		expand_all(result_count_with_folders > 64);
		
		console.log("FILTER TIME: " + (Date.now() - t0));
	}
	
	function filter_all_files() {
		if (!filtering) {
			setTimeout(apply_filters, 0);
			return;
		}
		if (idx >= num_files) {
			filter_finished(result_count);
			return;
		}
		
		var t0 = Date.now();
		for (var i = 0; i < filters_per_frame; i++) {
			if (filter_file()) {
				result_count++;
			}
			idx++;
			if (idx >= num_files) {
				filter_finished(result_count);
				return;
			}
		}
		var avg_filter_time = (Date.now() - t0) / filters_per_frame;
		filters_per_frame = Math.max(1, (16.67 / avg_filter_time));
		//filters_per_frame = 20;
		$('.load-count').text((idx+1));
		$('.load-percent').text("" + Math.floor((idx / num_files)*100));
		//console.log("BATCH: " + filters_per_frame + " FILTER TIME: " + avg_filter_time);
		setTimeout(filter_all_files, 0);
	}
	
	function filter_file() {
		var file = $(all_files[idx]);
		
		var ext = file.find(".name").text();
		ext = ext.substr(ext.lastIndexOf(".")+1).toLowerCase();
		var is_valid_ftype = false;
		for (var i = 0; i < valid_ftypes.length; i++)
		{
			if (ext.length == valid_ftypes[i].length && valid_ftypes[i].indexOf(ext) == 0)
			{
				is_valid_ftype = true;
				break;
			}
		}
		if (!is_valid_ftype) {
			file.addClass("exclude");
			return false;
		}
		
		if (author_name.length) {
			var found = false;
			$.each(file.find(".author"), function(idx, ref) {
				var name = $(ref).text().toLowerCase();
				if (name.indexOf(author_name) >= 0) {
					found = true;
				}
			});
			if (!found) {
				file.addClass("exclude");
				return false;
			}
		}
		if (file_name.length) {
			var name = file.find(".name").text().toLowerCase();
			if (name.indexOf(file_name) < 0) {
				file.addClass("exclude");
				return false;
			}
		}
		if (crc_name.length) {
			var name = file.attr("crc").toLowerCase();
			if (name.indexOf(crc_name) != 0) {
				file.addClass("exclude");
				return false;
			}
		}
		if (old_radio == 0 && file.find(".conflict").length) { file.addClass("exclude"); return false; }
		if (old_radio == 1 && !file.find(".conflict").length) { file.addClass("exclude"); return false; }
		if (extra_radio == 1 && file.find(".ref:not(.extra)").length) { file.addClass("exclude"); return false; }
		if (extra_radio == 0 && file.find(".ref.extra").length) { file.addClass("exclude"); return false; }
		if (share_radio == 0 && (file.find(".ref").length >= 2 || file.find(".conflict").length)) { file.addClass("exclude"); return false; }
		if (share_radio == 1 && file.find(".ref").length < 2 && !file.find(".conflict").length) { file.addClass("exclude"); return false; }
		file.removeClass("exclude");
		return true;
	}
	
	setTimeout(filter_all_files, 0);
}

function expand_all(collapse_instead) {
	$('.expand-btn, .collapse-btn').attr("disabled", "");
	var idx = 0;
	var delay = 0.1;
	var all_folders = $('.folder:not(.exclude)');
	if (!collapse_instead) {
		all_folders = all_folders.get().reverse();
	}
	var num_folders = all_folders.length;
	$.each(all_folders, function(i, dir) {
		setTimeout(function() {
			var content = $(dir).children(".content");
			if (!collapse_instead && $(dir).hasClass("closed")) {
				$(dir).removeClass("closed");
				content.show();
			} else if (collapse_instead && !$(dir).hasClass("closed")) {
				$(dir).addClass("closed");
				content.hide();
			}
			idx += 1;
		}, 0);
		
		delay += 0;
	});
	
	var expandInterval = setInterval(function() {
		if (idx == num_folders) {
			clearInterval(expandInterval);
			$('.expand-btn, .collapse-btn').removeAttr("disabled");
		}
	}, 10);
}

function post_load()
{
	$('.results-container').removeClass("invisible");
	
	function sort_func(x, y) {
		var isFolderA = $(x).hasClass("folder");
		var isFolderB = $(y).hasClass("folder");
		if (isFolderA != isFolderB) {
			return isFolderA ? -1 : 1;
		}
		
		var a = $(x).children("span").text().toLowerCase();
		var b = $(y).children("span").text().toLowerCase();
		
		return (a < b) ? -1 : (a > b) ? 1 : 0;
	}
	
	//file_tree = file_tree.find(".folder").sort(sort_func);
	
	$('#file-tree').append(file_tree);
	
	var ignore_checks = false;
	$('.filter-container input[type="radio"], .ftype').change(function() {
		if (!ignore_checks) {
			apply_filters();
		}
	});
	var filter_timeout;
	$('.crc-filter, .author-filter, .name-filter').keyup(function() {
		clearTimeout(filter_timeout);
		filter_timeout = setTimeout(apply_filters, 200);
	});
	$('.ftype-off-btn').click(function() {
		ignore_checks = true;
		$('.ftype').prop("checked", false);
		ignore_checks = false;
		apply_filters();
	});
	$('.ftype-on-btn').click(function() {
		ignore_checks = true;
		$('.ftype').prop("checked", true);
		ignore_checks = false;
		apply_filters();
	});
	$('.collapse-btn').click(function() {
		expand_all(true);
	});
	$('.expand-btn').click(function() {
		expand_all();
	});
	
	$('.folder > span').unbind("click");
	$('.folder > span').click(function() {
		var dir = $(this).parent();
		var content = dir.children(".content");
		dir.toggleClass("closed");
		if (!dir.hasClass("closed")) {
			content.slideDown("medium");
		} else {
			content.slideUp("medium");
		}
	});
	
	$('.share').click(function() {
		alert("Copy the URL in your address bar to share these results.\n\nThe bits after the '#' are your filter settings");

		return false;
	});
	
	//$('.loader, .loader-text').hide();
	
	apply_filters();
}

$( document ).ready( function() {

	load_hash_settings();
	
	$.getJSON("data.json", function(data1) {
		map_data = data1;
		console.log("Maps json: ", data1);
		
		$.getJSON("pool.json", function(data) {
			pool_data = data;
			console.log("Pool json: ", data);
			
			file_tree = write_tree(pool_data);
			file_tree = $($.parseHTML('<div>' + file_tree + '</div>'));
			
			var idx = 0;
			var loaded = 0;
			all_files = file_tree.find(".file").get();
			$('.load-total').text(num_files);
			$('.num-maps').text(num_files);
			var loads_per_frame = 10;
			function load_file() {
				var avg_load_time = 0;
				//var t0 = performance.now();
				var t0 = Date.now();
				for (var i = 0; i < loads_per_frame; i++) {
					var file = $(all_files[idx]);
					file.replaceWith(load_file_info(file.attr("key"), file.attr("path")));
					idx++;
					loaded++;
					if (idx >= num_files) {
						return;
					}
				}
				//var t = (performance.now() - t0) / loads_per_frame; // average load time for a file
				var t = (Date.now() - t0) / loads_per_frame;
				loads_per_frame = Math.max(1, (16.67 / t)); // tune next batch for 30fps
				//console.log("BATCH SIZE:" + loads_per_frame + " " + t);
				$('.load-count').text((loaded+1));
				$('.load-percent').text("" + Math.floor((loaded / num_files)*100));
				setTimeout(load_file, 0);
			}
			setTimeout(load_file, 0);
			
			$('.num-maps-container').removeClass("invisible");
			
			var load_interval = setInterval(function() {
				if (loaded >= num_files) {
					clearInterval(load_interval);
					all_files = file_tree.find(".file").get();
					post_load();
				}
			}, 10);
		});
	});
});