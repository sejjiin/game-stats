import untangle, statistics, sys, json, math
from scipy.stats import expon

LAMBDA = math.log(0.1) / -10.0

def h_index(plays_list):
	plays_desc = sorted(plays, reverse=True)
	h = 0
	while h + 1 < len(plays_desc) and h + 1 <= plays_desc[h]:
		h += 1
	return h

def friendless(plays_list):
	plays_heavy = len(list(filter(lambda x: x >= 10, plays_list)))
	plays_none = len(list(filter(lambda x: x == 0, plays_list)))
	plays_asc = sorted(plays_list)

	friendless_metric = 0
	if (plays_heavy < plays_none):
		friendless_metric = plays_heavy - plays_none
	elif (plays_heavy == len(plays_list)):
		friendless_metric = plays_asc[plays_heavy - 1]
	else:
		friendless_metric = plays_asc[plays_heavy]
	return friendless_metric

def load_xml_doc(bgg_username):
	url = "https://boardgamegeek.com/xmlapi2/collection?username=%s&own=1&excludesubtype=boardgameexpansion" \
	% bgg_username
	return untangle.parse(url)

def load_plays(xml_doc):
	plays = []
	for item in xml_doc.items.item:
		plays.append(int(item.numplays.cdata))
	return plays

def avg_cdf(plays_list):
	return statistics.mean(expon.cdf(plays_list, scale=1/LAMBDA))

def inverse_cdf(avg_cdf):
	inverse_cdf = -math.log(1 - float(avg_cdf))/.23
	return inverse_cdf

xml_doc = load_xml_doc(sys.argv[1])
plays = load_plays(xml_doc)
avg_cdf = avg_cdf(plays);
stats = {}
stats['h-index'] = h_index(plays)
stats['friendlessMetric'] = friendless(plays)
stats['continuousFriendlessMetric'] = round(inverse_cdf(avg_cdf), 2)
stats['utilization'] = round(avg_cdf, 3)
stats['mean'] = round(statistics.mean(plays), 2)
stats['median'] = statistics.median(plays)
print(json.dumps(stats, indent=2))