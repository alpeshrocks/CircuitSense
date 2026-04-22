CXX      = g++
CXXFLAGS = -std=c++17 -O2 -Wall
TARGETS  = circuit_parser sta_engine

all: $(TARGETS)

circuit_parser: circuit_parser.cpp
	$(CXX) $(CXXFLAGS) -o circuit_parser circuit_parser.cpp

sta_engine: sta_engine.cpp
	$(CXX) $(CXXFLAGS) -o sta_engine sta_engine.cpp

clean:
	rm -f $(TARGETS)
