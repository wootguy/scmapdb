// Globals
var num_moves = 0;
var num_deletes = 0;
var num_adds = 0;
var num_rec = 0;
var map_data = {}; 
var pool_data = {};
var all_maps; // All map divs
var total_maps = 0;

// controls & filters
var mapsPerPage = 20;
var pageNum = 0;
var maxPage = Math.ceil(total_maps / mapsPerPage) - 1;

var month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
var archive_ext = "zip";

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

function safe_map_name(name) {
	name = name.replace(/:/g, '-');
	name = name.replace(/</g, '-');
	name = name.replace(/>/g, '-');
	name = name.replace(/\*/g, '-');
	name = name.replace(/\//g, '-');
	name = name.replace(/\\/g, '-');
	name = name.replace(/\|/g, '-');
	name = name.replace(/"/g, '-');
	return name;
}

function write_tree(tree, pool_tree) {
	//console.log("WRITE TREE: ", tree);
	var out = '';
	
	for (var key in tree) {
		if (tree.hasOwnProperty(key)) {
			var is_leaf = typeof tree[key] != 'object'
			if (is_leaf) {
				type = parseInt(tree[key]) & 255
				flags = parseInt(tree[key]) &~255
				title = ''
				c = ''
				
				/*
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
				*/
				
				if (type == 1 || type == 10) {
					c = 'mod';
					title = type == 1 ? "File moved" : "File moved and/or renamed";
					num_moves += 1;
				} else if (type == 2 || type == 9) {
					if (type == 2) {
						title = "File added";
						num_adds += 1;
						c = 'add';
					}
					if (type == 9) {
						title = "File recovered from other map(s):\n";
						if (pool_tree && pool_tree[key] && pool_tree[key].refs) {
							for (var k = 0; k < pool_tree[key].refs.length; k++) {
								if (k > 0) {
									title += ', ';
								}
								title += pool_tree[key].refs[k].substr(1);
							}
						}
						else
							title = "File recovered from an unknown source (most likely an archive that was deleted from SCMapDB)";
						num_rec += 1;
						c = 'rec';
					}
					
				} else if (type != 0) {
					c = 'mov';
					if (type == 3) title = "File deleted (invalid extension)";
					if (type == 4) title = "File deleted (invalid location)";
					if (type == 5) title = "File deleted (unused / doesn't belong here)";
					if (type == 6) title = "File deleted (overwrites default content)";
					if (type == 7) title = "File deleted (not used in any map)";
					if (type == 8) title = "File deleted (moving to correct folder would overwrite another file with the same name)";
					num_deletes += 1;
				}
				
				out += '<div class="file" title="' + title + '"><span class="' + c + '">' + key + '</span>'
				if (flags & 256) {
					out +=' <span class="extra add" title="File added to extras archive">(E)</span>';
				}
				out += '</div>'
			} else {
				out += '<div class="folder"><div class="arrow"></div>'
				out += '<span>' + key + "</span>"
				out += write_tree(tree[key], pool_tree ? pool_tree[key] : undefined)
				out += '</div>'
			}
		}
	}
	
	return out;
}

function bind_map_div_clicks(map) {
	
	map.find('.folder > span').unbind("click");
	map.find('.folder > span').click(function() {
		$(this).parent().toggleClass("closed");
	});
}

function load_map_div_contents(map) {
	if (map.hasClass("loaded"))
		return;
	var key = map.attr("key");
	
	var jsonFile = "logs/" + safe_map_name(key) + ".json";
	
	console.log("downloading: " + jsonFile);
	var timestamp = new Date().getTime();
	jsonFile += "?_=" + timestamp; // prevent caching
	
	map.find(".db-page").attr("href", "http://scmapdb.com/map:" + key);
	map.find(".share").attr("href", "#map=" + encodeURIComponent(key));
	
	$.getJSON(jsonFile, function(detail) {
		bind_map_div_clicks(map);
		
		if (map.hasClass("loaded"))
			return;
		
		num_moves = num_deletes = 0;
		write_tree(detail['old_files'], pool_data);
		
		map.find(".old-tree-title .mod").text(num_moves + " moved");
		if (num_moves == 0)
			map.find(".old-tree-title .mod").removeClass("mod");
		
		map.find(".old-tree-title .mov").text(num_deletes + " deleted");
		if (num_deletes == 0)
			map.find(".old-tree-title .mov").removeClass("mov");
		
		num_adds = 0;
		num_rec = 0;
		write_tree(detail['new_files'], pool_data);
		
		map.find(".new-tree-title .add").text(num_adds + " added");
		map.find(".new-tree-title .rec").text(num_rec + " recovered");
		if (num_adds == 0)
			map.find(".new-tree-title .add").removeClass("add");
		if (num_rec == 0) {
			map.find(".new-tree-title .rec").removeClass("rec");
		}
		
		// Create res diffs
		var res_diff = detail['res_diff'];
		var num_add = 0;
		var num_rem = 0;
		if (res_diff) {
			var diff = '';
			for (var k in res_diff) {
				if (res_diff.hasOwnProperty(k)) {
					var map_diff = ''
					for (var i = 0; i < res_diff[k].length; i++) {
						if (!res_diff[k][i].length) {
							continue;
						}
						var val = res_diff[k][i].substring(1);
						var type = 'add';
						if (res_diff[k][i][0] == '-') {
							type = 'rem';
							num_rem += 1;
						} else {
							num_add += 1;
						}
						map_diff += '<span class="' + type + '">' + val + '</span><br>';
					}
					if (!map_diff.length) {
						map_diff = "No changes<br>";
					}
					diff += "<h3>" + k + ".res</h3>" + "<br>" + map_diff + "<br>";
				}	
			}
			map.find(".res-diff").html(diff);
			map.find(".diff-title .add").text(num_add + " added");
			map.find(".diff-title .rem").text(num_rem + " removed");
			if (num_add == 0)
				map.find(".diff-title .add").removeClass("add");
			if (num_rem == 0)
				map.find(".diff-title .rem").removeClass("rem");
		}
		
		// Create Resguy log
		var res_log = detail['resguy_log'];
		var missing_files = {};
		if (res_log) {
			res_log = res_log.replace(/\r\n/g, '<br>');
			res_log = res_log.replace(/\t/g, '<span class="tab"></span>');
			res_log = res_log.replace(/Missing file "/g, 'Missing file "<span class="rem">')
			res_log = res_log.replace(/" referenced in:/g, '</span>" referenced in:')
			res_log = $.parseHTML(res_log);

			map.find(".res-log").html(res_log);
			
			// only mark unique files
			$.each(map.find(".res-log").find(".rem"), function(idx, span) {
				var text = $(span).text();
				if (!(text in missing_files)) {
					missing_files[text] = true;
				} else {
					$(span).removeClass("rem");
				}
			});
		}
		
		// set up links
		var safe_name = safe_map_name(key);
		var d = new Date(parseInt(detail.scrape_date)*1000);
		var hours = d.getHours();
		var hsuffix = 'AM';
		if (hours > 12) {
			hours -= 12;
			hsuffix = 'PM';
		}
		var date = d.getDate() + ' ' + month_names[d.getMonth()] + ' ' + d.getFullYear();
		var time = hours + ':' + ('0'+d.getMinutes()).substr(-2) + ' ' + hsuffix;
		
		map.find(".scrape .date").text(date);
		map.find(".scrape .date").attr("title", time + " (this is when the archive was last downloaded and repacked)");
		map.find(".new-archive").attr("href", "https://w00tguy.no-ip.org/scmapdb/downloads/" + safe_name + "." + archive_ext);
		map.find(".old-archive").attr("href", "https://w00tguy.no-ip.org/scmapdb/cache/maps/" + safe_name + '.' + detail['old_ext']);
		map.find(".ext-archive").attr("href", "https://w00tguy.no-ip.org/scmapdb/downloads/" + safe_name + '_extras.' + archive_ext);
		map.find(".new-archive .size").text(pretty_size(detail['new_size']));
		
		var oldBytes = detail['old_size'];
		map.find(".old-archive .size").text(pretty_size(oldBytes));
		if (oldBytes === undefined) {
			map.find(".old-archive").addClass("no-link");
		}
		
		var extBytes = detail['extras_size'];
		map.find(".ext-archive .size").text(pretty_size(extBytes));
		if (extBytes === undefined) {
			map.find(".ext-archive").addClass("no-link");
		}
		
		var old_tree = $.parseHTML(write_tree(detail['old_files'], pool_data));
		var new_tree = $.parseHTML(write_tree(detail['new_files'], pool_data));
		map.find(".summary .old-tree").html(old_tree);
		map.find(".summary .new-tree").html(new_tree);
		
		map.addClass("loaded");
		
		bind_map_div_clicks(map);
	});
}

function load_map_div(map, key, map_data) {
	var total_other_changes = 0;
	//console.log("LOAD " + key);
	
	num_adds = map_data[key]['num_adds'];
	num_moves = map_data[key]['num_moves']; // so far these can only be for res files so not gonna add a filter for this yet
	num_resops = map_data[key]['num_resops'];
	num_changed = num_adds + num_moves + num_resops;
	num_deleted = map_data[key]['num_deleted'];
	num_recovered = map_data[key]['num_recovered'];
	overwrites_default = map_data[key]['overwrites_default'];
	
	if (num_adds > 0)
		map.find(".container").attr("added", num_adds);
	if (num_moves > 0)
		map.find(".container").attr("moved", num_moves);
	if (num_resops > 0)
		map.find(".container").attr("resops", num_resops);
	if (overwrites_default)
		map.find(".container").attr("overwrites", num_resops);
	
	if (num_deleted > 0) {
		map.find(".warnings").text(num_deleted + " Deleted");
		map.find(".container").attr("deleted", num_deleted);
	}
	
	var num_missing = map_data[key].missing || 0;
	if (num_missing > 0) {
		var plural = num_missing == 1 ? "" : "s";
		map.find(".missing-text").text(num_missing + " missing file" + plural);
		map.find(".missing-text").addClass("rem");
		map.find(".errors").text(num_missing + " Missing");
		map.find(".container").attr("missing", num_missing);
	}

	if (num_changed > 0)
		map.find(".infos").text(num_changed + " Changes");
	
	if (num_recovered > 0) {
		map.find(".recs").text(num_recovered + " Recovered");
		map.find(".container").attr("recovered", num_recovered);
	}
	
	if (map_data[key]['scripted']) {
		map.find(".scripted").text("Scripted!");
		map.find(".container").attr("scripted", 1);
	}
	
	var no_new_files = map_data[key]['no_maps']
	
	var num_problems = num_changed + (num_missing*1000) + (num_recovered*500) + (num_deleted*100);
	if (map_data[key]['map_pack'] || map_data[key]['default'])
		num_problems += 1;
	if (map_data[key]['failed'] || (no_new_files && !map_data[key]['default']))
		num_problems += 1000*1000;
		
	if (num_problems == 0)
	{
		map.find(".container").attr("perfect", "1");
		map.find(".perfect").text("Perfect Archive");
	}
	else
		map.find(".perfect").remove();
	map.find(".container").attr("issues", num_problems);
	map.find(".container").attr("key", key);
	map.find(".container").attr("sort-map", map_data[key]['title'].toLowerCase());
	map.find(".container").attr("sort-edit-time", map_data[key]['rev_time']);
	map.find(".container").attr("sort-author", map_data[key]['author'].toLowerCase());
	
	// write header
	if (map_data[key]['default']) {
		map.find(".mapname").addClass("default");
		map.find(".pack").text("Default Map");
		map.find(".pack").attr("title", "Map is included with Sven Co-op");
		map.find(".new-archive").addClass("no-link");
		map.find(".container").attr("default", "1");
	} else if (map_data[key]['failed']) {
		map.find(".mapname").addClass("failed");
		map.find(".errors").text("Download Failed");
		map.find(".errors").attr("title", "There were no active download links when the script last checked");
		map.find(".new-archive").addClass("no-link");
		map.find(".container").attr("err", "1");
	} else if (no_new_files) {
		map.find(".mapname").addClass("failed");
		map.find(".errors").text("No Maps");
		map.find(".errors").attr("title", "The archive had no maps inside");
		map.find(".new-archive").addClass("no-link");
		map.find(".container").attr("bad", "1");
	}
	map.find(".mapname").text(map_data[key]['title']);
	map.find(".author").text("by " + map_data[key]['author']);
	if (map_data[key]['map_pack']) {
		map.find(".pack").text("Map Pack");
		map.find(".container").attr("pack", "1");
	}
	
	map.find(".scrape .rev").text(map_data[key]['rev']);
	
	return map;
}

function loadPage() {
	collapse_maps();
	all_maps.detach();

	var filtered_maps = all_maps.not('.exclude');
	var start = 0 + pageNum*mapsPerPage;
	var end = Math.min(start + mapsPerPage, filtered_maps.length);
	if (mapsPerPage > 0) {
		maxPage = Math.ceil(filtered_maps.length / mapsPerPage) - 1;
	} else {
		maxPage = 0;
	}
	if (pageNum > maxPage) {
		pageNum = maxPage;
	}
	$('.map-tot').text("" + filtered_maps.length);
	
	$.each(filtered_maps, function(idx, map) {
		if (idx >= start && idx < end) {
			$(map).addClass("in-page");
			$('#accordion').append($(map));
		} else {
			$(map).removeClass("in-page");
		}
	});
	
	$('.page-start').text("" + (start+1));
	$('.page-end').text("" + end);
	$('.footer').find(".page-num-container").remove();
	$('.footer').append($(".page-num-container").clone());
	bind_nav_events();
	bind_click_handlers();
}

function collapse_maps() {
	$.each($('.container.active'), function(idx, row) {
		$(row).find(".summary").slideUp("medium");
		$(row).removeClass("active");
		$(row).animate({
			marginTop: 5,
			marginBottom: 5
		});
	});
}

function bind_click_handlers(){
	$(".expandable").unbind("click");
	$(".expandable").click(function() {
		var container = $(this).parents(".container");
		var summary = container.find(".summary");
		var opening = !container.hasClass("active");
	
		collapse_maps();
		
		if (opening)
		{
			load_map_div_contents($(this).parent());
			container.addClass("active");
			summary.slideDown("medium", function() {
				var offset = container.offset().top;
				var center = document.body.clientHeight - container.height();
				if (center > 0) {
					offset -= (center) / 2;
				}
				
				$('html,body').animate({
					scrollTop: offset
				});
			});
			
			container.animate({
				marginTop: 20,
				marginBottom: 20
			});						
		} 
	});
	
	$('.container .share').click(function() {		
		window.location.hash = $(this).attr("href").substr(1);
		
		$('.controls, .footer, .num-maps-container').addClass("hidden");
		$('.num-maps-container').addClass("invisible");
		$('.load-all-btn').removeClass("hidden");
		
		$('#accordion .container').not($(this).parents(".container")).remove();
		
		$('.load-all-btn').unbind("click");
		$('.load-all-btn').click(function() {
			$('.controls, .footer, .num-maps-container').removeClass("hidden");
			$('.num-maps-container').removeClass("invisible");
			$('.load-all-btn').addClass("hidden");
			
			$('#accordion .container').removeClass("active");
			$('#accordion .summary').hide();
			$('#accordion .container').css({
				marginTop: 5,
				marginBottom: 5
			});
			loadPage();
			
			window.location.hash = '';
		});
		
		return false;
	});
	
	$('.page-num-container .share').unbind("click");
	$('.page-num-container .share').click(function() {
		alert("Copy the URL in your address bar to share these results.\n\nThe bits after the '#' are your filter settings");
		
		return false;
	});
}

function bind_nav_events() {
	$('.page-prev-container').unbind("click");
	$('.page-next-container').unbind("click");
	$('.page-last-container').unbind("click");
	$('.page-first-container').unbind("click");
	
	$('.page-next-container').click(function() {
		if (pageNum >= maxPage) {
			pageNum = maxPage;
			return;
		}
		pageNum += 1;
		loadPage();
	});
	$('.page-prev-container').click(function() {
		if (pageNum <= 0) {
			pageNum = 0;
			return;
		}
		pageNum -= 1;
		loadPage();
	});
	
	$('.page-last-container').click(function() {
		if (pageNum == maxPage) {
			return;
		}
		pageNum = maxPage;
		loadPage();
	});
	$('.page-first-container').click(function() {
		if (pageNum == 0) {
			return;
		}
		pageNum = 0;
		loadPage();
	});
}

function sort_maps() {
	// sort everything
	var sorted;
	var reverse = $('.sort-dir option:selected').val() == "down";
	update_filter_hash();
	
	if ($('.sort-type option:selected').val() == "edit-time") {
		if (reverse) {
			sorted = all_maps.sort(function (x, y) {
				var a = x.getAttribute("sort-edit-time");
				var b = y.getAttribute("sort-edit-time");
				return (a < b) ? 1 : (a > b) ? -1 : 0;
			});
		} else {
			sorted = all_maps.sort(function (x, y) {
				var a = x.getAttribute("sort-edit-time");
				var b = y.getAttribute("sort-edit-time");
				return (a < b) ? -1 : (a > b) ? 1 : 0;
			});
		}
	}
	if ($('.sort-type option:selected').val() == "map") {
		if (reverse) {
			sorted = all_maps.sort(function (x, y) {
				var a = x.getAttribute("sort-map");
				var b = y.getAttribute("sort-map");
				return (a < b) ? 1 : (a > b) ? -1 : 0;
			});
		} else {
			sorted = all_maps.sort(function (x, y) {
				var a = x.getAttribute("sort-map");
				var b = y.getAttribute("sort-map");
				return (a < b) ? -1 : (a > b) ? 1 : 0;
			});
		}
	}
	if ($('.sort-type option:selected').val() == "author") {
		if (reverse) {
			sorted = all_maps.sort(function (x, y) {
				var a = x.getAttribute("sort-author");
				var b = y.getAttribute("sort-author");
				return (a < b) ? 1 : (a > b) ? -1 : 0;
			});
		} else {
			sorted = all_maps.sort(function (x, y) {
				var a = x.getAttribute("sort-author");
				var b = y.getAttribute("sort-author");
				return (a < b) ? -1 : (a > b) ? 1 : 0;
			});
		}
	}
	if ($('.sort-type option:selected').val() == "issues") {
		sorted = all_maps.sort(function (x, y) {
			var a = parseInt( x.getAttribute('issues') );
			var b = parseInt( y.getAttribute('issues') );
			var ret = (a < b) ? -1 : (a > b) ? 1 : 0;
			return reverse ? -ret: ret;
		});
	}
	
	pageNum = 0;
	loadPage();
}

function update_filter_hash() {
	var map_name = $('.map-filter').val().toLowerCase();
	var author_name = $('.author-filter').val().toLowerCase();
	var miss_radio = parseInt( $('input[name="miss-radio"]:checked').val() );
	var del_radio = parseInt( $('input[name="del-radio"]:checked').val() );
	var rec_radio = parseInt( $('input[name="rec-radio"]:checked').val() );
	var dl_radio = parseInt( $('input[name="dl-radio"]:checked').val() );
	var pack_radio = parseInt( $('input[name="pack-radio"]:checked').val() );
	var def_radio = parseInt( $('input[name="default-radio"]:checked').val() );
	var perf_radio = parseInt( $('input[name="perfect-radio"]:checked').val() );
	var mov_radio = parseInt( $('input[name="mov-radio"]:checked').val() );
	var res_radio = parseInt( $('input[name="res-radio"]:checked').val() );
	var script_radio = parseInt( $('input[name="script-radio"]:checked').val() );
	var overwrite_radio = parseInt( $('input[name="overwrite-radio"]:checked').val() );
	
	var sort_type = "" + ($('.sort-type option:selected').index()+1);
	var sort_dir = "" + ($('.sort-dir option:selected').index()+1);
	
	var hash = "#" + encodeURIComponent(map_name) + "&" + encodeURIComponent(author_name);
	hash += "&" + miss_radio + rec_radio + del_radio + dl_radio + pack_radio + def_radio + perf_radio;
	hash += sort_type + sort_dir + mov_radio + res_radio + script_radio + overwrite_radio;
	
	$('.page-num-container .share').attr("href", hash);
	window.location.hash = hash;
}

function load_hash_settings() {
	var hash = window.location.hash.substr(1);
	var filters = hash.split("&");
	
	if (filters.length <= 1) {
		return;
	}
	
	if (filters.length != 3 || (filters[2].length != 9 && filters[2].length != 13)) {
		console.log("Invalid filter settings " + filters[2].length);
		return;
	}
	console.log("Applying URL filters");
	
	$('.map-filter').val(decodeURIComponent(filters[0]));
	$('.author-filter').val(decodeURIComponent(filters[1]));
	
	filters = filters[2];
	
	$('input[name="miss-radio"][value="' + filters[0] + '"]').prop("checked", true);
	$('input[name="rec-radio"][value="' + filters[1] + '"]').prop("checked", true);
	$('input[name="del-radio"][value="' + filters[2] + '"]').prop("checked", true);
	$('input[name="dl-radio"][value="' + filters[3] + '"]').prop("checked", true);
	$('input[name="pack-radio"][value="' + filters[4] + '"]').prop("checked", true);
	$('input[name="default-radio"][value="' + filters[5] + '"]').prop("checked", true);
	$('input[name="perfect-radio"][value="' + filters[6] + '"]').prop("checked", true);
	
	$('.sort-type option:nth-child(' + filters[7] + ')').attr("selected", "selected");
	$('.sort-dir option:nth-child(' + filters[8] + ')').attr("selected", "selected");
	
	// new filters added last to prevent old links from breaking
	if (filters.length > 9) {
		$('input[name="mov-radio"][value="' + filters[9] + '"]').prop("checked", true);
		$('input[name="res-radio"][value="' + filters[10] + '"]').prop("checked", true);
		$('input[name="script-radio"][value="' + filters[11] + '"]').prop("checked", true);
		$('input[name="overwrite-radio"][value="' + filters[12] + '"]').prop("checked", true);
	}
	
	apply_filters();
}

function apply_filters() {
	var map_name = $('.map-filter').val().toLowerCase();
	var author_name = $('.author-filter').val().toLowerCase();
	var miss_radio = parseInt( $('input[name="miss-radio"]:checked').val() );
	var del_radio = parseInt( $('input[name="del-radio"]:checked').val() );
	var rec_radio = parseInt( $('input[name="rec-radio"]:checked').val() );
	var dl_radio = parseInt( $('input[name="dl-radio"]:checked').val() );
	var pack_radio = parseInt( $('input[name="pack-radio"]:checked').val() );
	var def_radio = parseInt( $('input[name="default-radio"]:checked').val() );
	var perf_radio = parseInt( $('input[name="perfect-radio"]:checked').val() );
	var mov_radio = parseInt( $('input[name="mov-radio"]:checked').val() );
	var res_radio = parseInt( $('input[name="res-radio"]:checked').val() );
	var script_radio = parseInt( $('input[name="script-radio"]:checked').val() );
	var overwrite_radio = parseInt( $('input[name="overwrite-radio"]:checked').val() );
	all_maps.removeClass("in-page");
	all_maps.removeClass("exclude");
	
	update_filter_hash();
	
	$.each(all_maps, function(idx, map) {
		map = $(map);
		if (map_name.length) {
			var name = map.find(".mapname").text().toLowerCase();
			if (name.indexOf(map_name) < 0) {
				map.addClass("exclude");
			}
		}
		if (author_name.length) {
			var name = map.find(".author").text().toLowerCase();
			if (name.indexOf(author_name) < 0) {
				map.addClass("exclude");
			}
		}
		if (miss_radio == 0 && (!!map.attr('missing'))) { map.addClass("exclude"); }
		if (miss_radio == 1 && !(!!map.attr('missing'))) { map.addClass("exclude"); }
		if (del_radio == 0 && (!!map.attr('deleted'))) { map.addClass("exclude"); }
		if (del_radio == 1 && !(!!map.attr('deleted'))) { map.addClass("exclude"); }
		if (rec_radio == 0 && (!!map.attr('recovered'))) { map.addClass("exclude"); }
		if (rec_radio == 1 && !(!!map.attr('recovered'))) { map.addClass("exclude"); }
		if (dl_radio == 0 && !(!!map.attr('err'))) { map.addClass("exclude"); }
		if (dl_radio == 1 && (!!map.attr('err'))) { map.addClass("exclude"); }
		if (pack_radio == 0 && (!!map.attr('pack'))) { map.addClass("exclude"); }
		if (pack_radio == 1 && !(!!map.attr('pack'))) { map.addClass("exclude"); }
		if (def_radio == 0 && (!!map.attr('default'))) { map.addClass("exclude"); }
		if (def_radio == 1 && !(!!map.attr('default'))) { map.addClass("exclude"); }
		if (perf_radio == 0 && (!!map.attr('perfect'))) { map.addClass("exclude"); }
		if (perf_radio == 1 && !(!!map.attr('perfect'))) { map.addClass("exclude"); }
		if (mov_radio == 0 && (!!map.attr('moved'))) { map.addClass("exclude"); }
		if (mov_radio == 1 && !(!!map.attr('moved'))) { map.addClass("exclude"); }
		if (res_radio == 0 && (!!map.attr('resops'))) { map.addClass("exclude"); }
		if (res_radio == 1 && !(!!map.attr('resops'))) { map.addClass("exclude"); }
		if (script_radio == 0 && (!!map.attr('scripted'))) { map.addClass("exclude"); }
		if (script_radio == 1 && !(!!map.attr('scripted'))) { map.addClass("exclude"); }
		if (overwrite_radio == 0 && (!!map.attr('overwrites'))) { map.addClass("exclude"); }
		if (overwrite_radio == 1 && !(!!map.attr('overwrites'))) { map.addClass("exclude"); }
	});
	
	pageNum = 0;
	loadPage();
}

function compare_trees(tree1, tree2, path) {
	//console.log("WRITE TREE: ", tree);
	var same = true;
	if (!path) {
		path = "";
	}
	
	for (var key in tree1) {
		if (tree1.hasOwnProperty(key)) {
			if (!tree2.hasOwnProperty(key)) {
				console.log(path + key + "(NEW KEY)");
				return false;
			}
			var is_leaf = typeof tree1[key] != 'object';
			if (is_leaf) {
				if (tree1[key] != tree2[key]) {
					console.log(path + key + " (" + tree1[key] + " != " + tree2[key] + ")");
					return false;
				}
			} else {
				if (!compare_trees(tree1[key], tree2[key], path + key + "/"))
				{
					return false;
				}
			}
		}
	}
	
	for (var key in tree2) {
		if (tree2.hasOwnProperty(key) && !tree1.hasOwnProperty(key)) {
			if (!tree2.hasOwnProperty(key)) {
				console.log(path + key + "(DEL KEY)");
				return false;
			}
		}
	}
	
	return same;
}

function compare_jsons() {
	$.getJSON("data_new.json", function(data) {
		var map_data2 = data;
		var map_diff = {};
		
		console.log("LOADED NEW JSON");
		
		for (var key in map_data2) {
			if (map_data2.hasOwnProperty(key)) {
				if (!map_data.hasOwnProperty(key)){
					console.log("NEW MAP: " + key);
					continue;
				}
				var diff_types = "";
				
				var old_tree1 = map_data[key]['old_files'];
				var old_tree2 = map_data2[key]['old_files'];				
				if (!compare_trees(old_tree1, old_tree2)) {
					diff_types += "old_files ";
				}
				
				var new_tree1 = write_tree(map_data[key]['new_files']);
				var new_tree2 = write_tree(map_data2[key]['new_files']);
				if (!compare_trees(new_tree1, new_tree2)) {
					diff_types += "new_files ";
				}

				// compare missing files
				var res_log1 = map_data[key]['resguy_log'];
				var res_log2 = map_data2[key]['resguy_log'];
				function get_missing_files(res_log) {
					if (!res_log) {
						return {};
					}
					res_log = res_log.replace(/\r\n/g, '<br>');
					res_log = res_log.replace(/\t/g, '<span class="tab"></span>');
					res_log = res_log.replace(/Missing file "/g, 'Missing file "<span class="rem">')
					res_log = res_log.replace(/" referenced in:/g, '</span>" referenced in:')
					res_log = $.parseHTML(res_log);

					var res_div = $($(res_log).wrap('<div/>'));
					
					var missing_files = {};
					$.each(res_div.find(".rem"), function(idx, span) {
						var text = $(span).text();
						if (!(text in missing_files)) {
							missing_files[text] = true;
						}
					});
					return missing_files;
				}
				var same = true;
				var missing_files1 = get_missing_files(res_log1);
				var missing_files2 = get_missing_files(res_log2);
				for (var key in missing_files1) {
					if (missing_files1.hasOwnProperty(key) && !missing_files2.hasOwnProperty(key)) {
						same = false;
						console.log("NO LONGER MISSING: " + key);
						diff_types += "resguy_log ";
						break;
					}
				}
				if (same) {
					for (var key in missing_files2) {
						if (missing_files2.hasOwnProperty(key) && !missing_files1.hasOwnProperty(key)) {
							same = false;
							console.log("NEW MISSING: " + key);
							diff_types += "resguy_log ";
							break;
						}
					}
				}
					
				var res_diff1 = map_data[key]['res_diff'];
				var res_diff2 = map_data2[key]['res_diff'];
				for (var k in res_diff2) {
					if (res_diff2.hasOwnProperty(k)) {
						if (!res_diff2.hasOwnProperty(k)) {
							diff_types += "res_diff ";
							break;
						}
						
						var diff1 = res_diff1[k];
						var diff2 = res_diff2[k];
						var not_same = false;
						for (var c in diff2) {
							if (!$.inArray(c, diff1)) {
								diff_types += "res_diff ";
								not_same = true;
								break;
							}
						}
						if (not_same) {
							break;
						}
					}
				}
				
				var map = all_maps.filter('[key="' + key + '"]');
				if (diff_types.length) {
					console.log(key + " DIFFS: " + diff_types);
					console.log("");
					map.find(".mapname").text(map.find(".mapname").text() + " (OLD)");
					var newmap = load_map_div( $(".template").clone(), key, map_data2 );
					all_maps = all_maps.add($(newmap.html()));
				} else {
					map.remove();
					all_maps = all_maps.not('[key="' + key + '"]');
				}
			}
		}
		
		console.log("OK LOAD IT");
		sort_maps();
	});
}

$( document ).ready( function() {

	$('.repack_but').click(function() {
		console.log("COMMENCE THE REPACK");
		
		$('.repack-dialog .output').text("");
		$('.repack-dialog').removeClass("hidden");
		$('.repack-dialog .status-text').text("Updating...");
		$('.repack-dialog .loader2').removeClass("hidden");
		$(this).height(Math.floor($(this).height()/2)*2);
		
		var last_response_len = false;
		$.ajax('https://w00tguy.no-ip.org/scmapdb/manual_update.php', {
			xhrFields: {
				onprogress: function(e)
				{
					var this_response, response = e.currentTarget.response;
					if(last_response_len === false)
					{
						this_response = response;
						last_response_len = response.length;
					}
					else
					{
						this_response = response.substring(last_response_len);
						last_response_len = response.length;
					}
					//console.log(this_response);
					var new_text = $('.repack-dialog .output').text() + this_response;
					$('.repack-dialog .output').html(new_text);
					$('.repack-dialog .output').scrollTop($('.repack-dialog .output')[0].scrollHeight);
				}
			}
		})
		.done(function(data)
		{
			$('.repack-dialog .status-text').text("Update finished");
			$('.repack-dialog .loader2').addClass("hidden");
			$('.repack-dialog .output').html(data);
			$('.repack-dialog .output').scrollTop($('.repack-dialog .output')[0].scrollHeight);
			console.log('Request finished');
		})
		.fail(function(data)
		{
			$('.repack-dialog .loader2').addClass("hidden");
			$('.repack-dialog .status-text').text("Update failed");
			console.log('Error: ', data);
		});
	});
	$('.repack-dialog button').click(function() {
		location.reload();
	});

	var url_string = window.location.href;
	var url = new URL(url_string);
	var jsonFile = url.searchParams.get("file");
	if (!jsonFile)
		jsonFile = "data.json";
	console.log("Using data file: " + jsonFile);

	console.log("Downloading pool json");
	$.getJSON("pool.json", function(pool_dat) {
		pool_data = pool_dat;
		
		console.log("Downloading map json");
		var timestamp = new Date().getTime();
		jsonFile += "?_=" + timestamp; // prevent caching
		$.getJSON(jsonFile, function(data) {
			map_data = data;
			console.log("Map json: ", data);
			
			// count maps and give feedback for JSON load finishing
			for (var key in map_data) {
				if (map_data.hasOwnProperty(key)) {
					total_maps += 1;
				}
			}
			$('.num-maps').text("" + total_maps);
			$('.map-tot').text("" + total_maps);
			
			// Bind control events
			$('.map-filter, .author-filter').keyup(function() {
				apply_filters();
			});
			$('.filter-container input[type="radio"]').change(function() {
				apply_filters();
			});
			$('.max-page-amt').keyup(function() {
				mapsPerPage = parseInt($(this).val());
				if (isNaN(mapsPerPage)) {
					mapsPerPage = 0;
				}
				loadPage();
			});
			$('.sort-dir, .sort-type').change(function() {
				sort_maps();
			});
			$('.eye-rape').change(function() {
				if ($(this).is(":checked")) {
					all_maps.find('.perfect').addClass("rape");
				} else {
					all_maps.find('.perfect').removeClass("rape");
				}
			});
			$('.compare-btn').click(function() {
				compare_jsons();
			});
			
			// load all the map result info
			var idx = 0;
			var numLoaded = 0;
			var load_counter = $('.load-count');
			var load_percent = $('.load-percent');
			$('.load-total').text(total_maps);
			all_maps = $([]);
			function load_map(key) {
				var map = load_map_div( $(".template").clone(), key, map_data );
				all_maps.push($(map.html()));
				numLoaded += 1;
				load_counter.text((numLoaded+1));
				load_percent.text("" + Math.floor((numLoaded / total_maps)*100));
			}
			
			var all_keys = [];
			for (var key in map_data) {
				if (map_data.hasOwnProperty(key)) {
					all_keys.push(key);
				}
			}
			var num_keys = all_keys.length;
			
			var loads_per_frame = 50;
			
			function finish_load() {
				$('.num-maps-container').removeClass("invisible");
				//all_maps = $('#accordion .container');
				//all_maps = $(all_maps);
				all_maps = all_maps.map(function(){
					return this.toArray();
				});
				
				load_hash_settings();
				sort_maps();
				loadPage();
				$('.loader, .loader-text').addClass("hidden");
				$('.controls, .footer').removeClass("hidden");
				
				/*
				$.each(all_maps, function(idx, div) {
					// DEBUG: So I know which idx to use in the script
					$(div).find('.mapname').text( idx + ": " + $(div).find('.mapname').text() );
				});
				*/
			}
			
			function load_all_maps()
			{
				if (idx >= num_keys) {
					finish_load();
					return;
				}
				
				var t0 = Date.now();
				for (var i = 0; i < loads_per_frame; i++) {
					load_map(all_keys[idx]);
					idx += 1;
					
					if (idx >= num_keys) {
						finish_load();
						loaded_all_maps = true;
						return;
					}
				}
				var t = (Date.now() - t0) / loads_per_frame;
				loads_per_frame = Math.max(1, 16.67 / t);
				setTimeout(load_all_maps, 0);
			}
			
			var loaded_all_maps = false;
			
			var hash = window.location.hash.substr(1);
			if (hash.indexOf("map=") == 0) {
				// Just load the map that was shared
				var map = decodeURIComponent(hash.substr(hash.indexOf("=") + 1));
				if (map_data[map]) {
					load_map(map);
					finish_load();
					
					$('.controls, .footer, .num-maps-container').addClass("hidden");
					$('.num-maps-container').addClass("invisible");
					$('.load-all-btn').removeClass("hidden");
					
					// automatically expand result
					$('#accordion .container').addClass("active");
					$('#accordion .summary').show();
					load_map_div_contents($('#accordion .container'));
					
					// make use of the extra space
					
					$('.load-all-btn').click(function() {
						window.location.hash = '';
						$('#accordion .container').remove();
						all_maps = $([]);
						numLoaded = 0;
						$(this).addClass("hidden");
						$('.loader, .loader-text, .num-maps-container').removeClass("hidden");
						load_all_maps();
					});
				} else {
					load_all_maps();
				}
			} else {
				load_all_maps();
			}

			//$($('.container')[0]).click();
		});
	});	
});