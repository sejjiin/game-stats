import bgg, sys, statistics

def suggested_coll_size(h_index, mean, median):
	return 2 * (h_index + mean + median)

xml_doc = bgg.load_xml_doc(sys.argv[1])
plays = bgg.load_plays(xml_doc)
h_index = bgg.h_index(plays)
mean = statistics.mean(plays)
median = statistics.median(plays)
coll_size = len(xml_doc.items)
suggested_coll_size = suggested_coll_size(h_index, mean, median)
print("Collection size: %s"%coll_size)
print("Suggested Collection Size: %s"%round(suggested_coll_size, 2))
print("Delta: %s game(s)"%int(suggested_coll_size - coll_size))