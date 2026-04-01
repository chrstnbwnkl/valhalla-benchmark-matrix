### Categorizing Matrix Requests by Location count and Geographical Extent 

These requests are put into one of 9 buckets, each representing a cell in our location-count/geographical-extent matrix. The first digit in the directory refers to the location count, the second to the geographical extent where 0=few/small and 2=many/large. 

Note that geographical extent is a bit of a proxy for the number of edges explored during an expansion, but for sake of simplicity, let's use this single factor that influences how much graph exploration we have to do instead of something more complex (such as extent + costing + hierarchy limits + road network density etc etc).
