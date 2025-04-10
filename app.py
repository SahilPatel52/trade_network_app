# app.py
from flask import Flask, render_template, request # Added request
import pymongo
import os
import pandas as pd
from collections import defaultdict # Added for easier processing
import traceback # For detailed error printing
import networkx as nx # Add this import at the top of app.py
from networkx.algorithms import community as nx_community # Use alias to avoid name conflicts

# Initialize the Flask application
app = Flask(__name__)

# --- MongoDB Configuration ---
MONGO_URI = os.environ.get('MONGO_URI') # NEW LINE using environment variable

# Initialize MongoDB Client
db_status = "MongoDB status unknown"
client = None
db = None
try:
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ismaster')
    db_status = "MongoDB connection successful!"
    db = client['trade_db']
except pymongo.errors.ConnectionFailure as e:
    print(f"Could not connect to MongoDB: {e}")
    db_status = f"MongoDB connection failed: {e}"
    client = None
except Exception as e:
    print(f"An error occurred during MongoDB initialization: {e}")
    db_status = f"MongoDB initialization error: {e}"
    client = None

# --- Get Distinct Country List (Run Once at Startup - Improved) ---
distinct_countries = []
if db is not None: # Check if db connection exists
    try:
        print("Fetching distinct country list (reporters and partners) from MongoDB...")
        pipeline = [
            {'$match': {'reporter': {'$ne': 'World'}, 'partner': {'$ne': 'World'}}}, # Exclude 'World'
            {'$group': {'_id': None, 'reporters': {'$addToSet': '$reporter'}, 'partners': {'$addToSet': '$partner'}}},
            {'$project': {'allCountries': {'$setUnion': ['$reporters', '$partners']}, '_id': 0}}
        ]
        result = list(db.trade_records.aggregate(pipeline))
        if result and 'allCountries' in result[0]:
            distinct_countries = sorted(result[0]['allCountries'])
            print(f"Found {len(distinct_countries)} distinct countries (reporters/partners).")
        else:
             print("Could not retrieve distinct countries, falling back to reporters only.")
             distinct_countries = sorted(db.trade_records.distinct("reporter", {"reporter": {"$ne": "World"}}))
    except Exception as e:
        print(f"Error fetching distinct countries: {e}")
        distinct_countries = ["Error fetching countries"]
else:
    print("Skipping country list fetch: No MongoDB connection.")
    distinct_countries = ["DB connection failed"]
# --- End of Get Distinct Country List ---


"""
# --- Load Trade Data --- (This section should remain commented out for normal runs)
# ... (your previously commented out data loading/processing code) ...
"""


# --- Routes ---
@app.route('/')
def index():
    # Pass the enhanced country list to the index template
    return render_template('index.html',
                           db_status=db_status,
                           countries=distinct_countries)


@app.route('/country_detail')
def country_detail():
    # ... (Code for single country view with mirror flows - from previous step) ...
    selected_country = request.args.get('country_name')
    partner_data = defaultdict(lambda: {'export': 0, 'import': 0, 'balance': 0, 'export_reported': False, 'import_reported': False})
    world_data = {'export': 0, 'import': 0, 'balance': 0, 'export_reported': False, 'import_reported': False, 'export_calculated': False, 'import_calculated': False}
    error_message = None
    trade_year = "N/A"

    if not selected_country:
        error_message = "No country selected."
    elif db is None:
        error_message = "Database connection not available."
    else:
        try:
            print(f"Processing data for: {selected_country}")
            # 1. Get DIRECT data
            print("Fetching direct data...")
            direct_cursor = db.trade_records.find({'reporter': selected_country})
            direct_data_found = False
            for record in direct_cursor:
                direct_data_found = True
                trade_year = record['year']
                partner = record['partner']
                flow = record['flow']
                value = record['value']
                if partner == "World":
                    if flow == "Export": world_data['export'] = value; world_data['export_reported'] = True
                    elif flow == "Import": world_data['import'] = value; world_data['import_reported'] = True
                else:
                    if flow == "Export": partner_data[partner]['export'] = value; partner_data[partner]['export_reported'] = True
                    elif flow == "Import": partner_data[partner]['import'] = value; partner_data[partner]['import_reported'] = True
            print(f"Direct data found: {direct_data_found}")

            # 2. Get MIRROR data
            print("Fetching mirror data...")
            mirror_cursor = db.trade_records.find({'partner': selected_country})
            mirror_data_found = False
            for record in mirror_cursor:
                mirror_data_found = True
                trade_year = record['year']
                reporter_as_partner = record['reporter']
                flow = record['flow']
                value = record['value']
                if flow == "Export": # Partner exported TO selected_country -> Selected country's IMPORT
                    if not partner_data[reporter_as_partner]['import_reported']: partner_data[reporter_as_partner]['import'] = value
                elif flow == "Import": # Partner imported FROM selected_country -> Selected country's EXPORT
                    if not partner_data[reporter_as_partner]['export_reported']: partner_data[reporter_as_partner]['export'] = value
            print(f"Mirror data found: {mirror_data_found}")

            # 3. Calculate Balances for Partners
            print("Calculating partner balances...")
            final_partner_data = dict(partner_data)
            for partner, data in final_partner_data.items(): data['balance'] = data['export'] - data['import']

            # 4. Calculate World Totals if direct data wasn't found
            print("Checking and calculating World totals...")
            calculated_world_export = 0; calculated_world_import = 0
            if not world_data['export_reported'] or not world_data['import_reported']:
                print("Direct World data incomplete, calculating from partners...")
                for partner, data in final_partner_data.items():
                    calculated_world_export += data.get('export', 0)
                    calculated_world_import += data.get('import', 0)
                if not world_data['export_reported']:
                    world_data['export'] = calculated_world_export; world_data['export_calculated'] = True
                    print(f"Calculated World Export Total: {calculated_world_export}")
                if not world_data['import_reported']:
                    world_data['import'] = calculated_world_import; world_data['import_calculated'] = True
                    print(f"Calculated World Import Total: {calculated_world_import}")
            world_data['balance'] = world_data['export'] - world_data['import']
            print(f"Final World Data: {world_data}")

            if not direct_data_found and not mirror_data_found: error_message = f"No trade data found involving {selected_country} as reporter or partner."

        except Exception as e:
            error_message = f"Error processing data for {selected_country}: {e}\n{traceback.format_exc()}"; print(error_message)

    return render_template('country_view.html',
                           selected_country=selected_country, year=trade_year,
                           world_data=world_data, partner_data=final_partner_data,
                           error=error_message)


# --- NEW: Route for Two-Country Comparison ---
@app.route('/compare')
def compare_countries():
    country_A = request.args.get('country_A')
    country_B = request.args.get('country_B')
    trade_data = None # Initialize as None
    error_message = None
    trade_year = "N/A"

    if not country_A or not country_B:
        error_message = "Please select two countries to compare."
    elif country_A == country_B:
        error_message = "Please select two different countries."
    elif db is None:
        error_message = "Database connection not available."
    else:
        try:
            print(f"Comparing trade between {country_A} and {country_B}")

            # Helper function (can be defined outside or inside, careful with scope if outside)
            def get_trade_value(reporter, partner, flow_desc):
                # Try direct report first
                direct_query = {'reporter': reporter, 'partner': partner, 'flow': flow_desc}
                direct_result = db.trade_records.find_one(direct_query)
                if direct_result:
                    return direct_result.get('value', 0), True, direct_result.get('year', None)

                # If direct not found, try mirror report
                mirror_flow_desc = "Import" if flow_desc == "Export" else "Export"
                mirror_query = {'reporter': partner, 'partner': reporter, 'flow': mirror_flow_desc}
                mirror_result = db.trade_records.find_one(mirror_query)
                if mirror_result:
                    return mirror_result.get('value', 0), False, mirror_result.get('year', None)

                # If neither found
                return 0, False, None

            # Get A -> B flow (A's Export to B), prioritize A's report
            A_to_B_value, A_to_B_reported, year1 = get_trade_value(country_A, country_B, "Export")

            # Get B -> A flow (B's Export to A), prioritize B's report
            # This value represents A's Imports from B
            B_to_A_value, B_to_A_reported, year2 = get_trade_value(country_B, country_A, "Export")

            # Determine the year (use valid year if found)
            trade_year = year1 if year1 is not None else year2 if year2 is not None else "N/A"
            if isinstance(trade_year, list): trade_year = trade_year[0] # Handle potential list if $first was used

            # Calculate balance from A's perspective (A's Exports - A's Imports)
            balance = A_to_B_value - B_to_A_value

            trade_data = {
                'A_to_B_value': A_to_B_value,
                'A_to_B_reported': A_to_B_reported, # True if A reported Export to B
                'B_to_A_value': B_to_A_value,
                'B_to_A_reported': B_to_A_reported, # True if B reported Export to A
                'balance': balance
            }
            print(f"Comparison data: {trade_data}")

        except Exception as e:
            error_message = f"Error processing comparison for {country_A} and {country_B}: {e}\n{traceback.format_exc()}"
            print(error_message)

    return render_template('compare_view.html',
                            country_A=country_A,
                            country_B=country_B,
                            year=trade_year,
                            trade_data=trade_data, # Pass dictionary directly
                            error=error_message)


# Keep other routes for testing
@app.route('/data')
def show_data():
    # ... (previous code for /data) ...
    records_list = []
    error_message = None
    if db is not None:
        try:
            trade_cursor = db.trade_records.find().sort('value', pymongo.DESCENDING).limit(20)
            records_list = list(trade_cursor)
            print(f"Retrieved {len(records_list)} records from MongoDB for display.")
        except Exception as e:
            error_message = f"Error querying MongoDB: {e}"
            print(error_message)
    else:
        error_message = "Database connection not available."
    return render_template('trade_data.html', records=records_list, error=error_message)


@app.route('/test_db')
def test_db_connection():
    # ... (previous code for /test_db) ...
    if client and db is not None:
        try:
            collection_names = db.list_collection_names()
            count = 0
            if 'trade_records' in collection_names:
                count = db['trade_records'].count_documents({})
            return f"MongoDB Connected! DB: 'trade_db'. Collections: {collection_names}. Records in 'trade_records': {count}"
        except Exception as e:
            return f"Connected, but error listing collections/counting documents: {e}"
    else:
        return "Failed to establish connection with MongoDB client or database."
    

@app.route('/network_analysis')
def network_analysis():
    error_message = None
    centrality_results = {} # Dictionary to hold centrality results
    community_results = [] # List to hold communities
    graph_info = {} # Dictionary for basic graph info

    if db is None:
        error_message = "Database connection not available."
    else:
        try:
            print("Fetching data for network graph construction...")
            query = {
                "partner": {"$ne": "World"}, "reporter": {"$ne": "World"},
                "flow": "Export", "value": {"$gt": 0}
            }
            projection = {"_id": 0, "reporter": 1, "partner": 1, "value": 1}
            trade_data = list(db.trade_records.find(query, projection))

            if not trade_data:
                error_message = "No suitable trade data found in database to build network (check filters)."
            else:
                print(f"Building network graph from {len(trade_data)} export records...")
                G = nx.DiGraph() # Directed graph
                for record in trade_data:
                    G.add_edge(record['reporter'], record['partner'], weight=record['value'])

                # Ensure graph is not empty before proceeding
                if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
                     error_message = "Graph could not be built (no valid nodes/edges)."
                else:
                    print(f"Graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
                    graph_info['nodes'] = G.number_of_nodes()
                    graph_info['edges'] = G.number_of_edges()

                    # --- Calculate Centralities ---
                    top_n = 20
                    # Degree
                    print("Calculating In/Out Degree...")
                    in_degree = dict(G.in_degree())
                    out_degree = dict(G.out_degree())
                    centrality_results['in_degree'] = sorted(in_degree.items(), key=lambda item: item[1], reverse=True)[:top_n]
                    centrality_results['out_degree'] = sorted(out_degree.items(), key=lambda item: item[1], reverse=True)[:top_n]
                    # Betweenness
                    print("Calculating Betweenness Centrality (weighted)...")
                    try:
                        betweenness = nx.betweenness_centrality(G, weight='weight', normalized=True)
                        centrality_results['betweenness'] = sorted(betweenness.items(), key=lambda item: item[1], reverse=True)[:top_n]
                        print("Betweenness calculation complete.")
                    except Exception as e_between:
                        print(f"Error calculating betweenness centrality: {e_between}")
                        centrality_results['betweenness'] = [("Calculation Error", f"{e_between}")]
                    # Eigenvector
                    print("Calculating Eigenvector Centrality (weighted)...")
                    try:
                        eigenvector = nx.eigenvector_centrality(G, weight='weight', max_iter=1000, tol=1e-03)
                        centrality_results['eigenvector'] = sorted(eigenvector.items(), key=lambda item: item[1], reverse=True)[:top_n]
                        print("Eigenvector calculation complete.")
                    except nx.PowerIterationFailedConvergence as e_eigen_conv:
                        print(f"Eigenvector Centrality did not converge: {e_eigen_conv}")
                        centrality_results['eigenvector'] = [("Convergence Error", f"{e_eigen_conv}")]
                    except Exception as e_eigen:
                        print(f"Error calculating eigenvector centrality: {e_eigen}")
                        centrality_results['eigenvector'] = [("Calculation Error", f"{e_eigen}")]

                    # --- Calculate Communities (Louvain) ---
                    print("Calculating Communities (Louvain method)...")
                    try:
                        # Use Louvain on the undirected version for standard algorithm application,
                        # weighting edges appropriately. Consider resolution parameter if needed.
                        # Louvain works best on undirected graphs, using weights.
                        communities_generator = nx_community.louvain_communities(G.to_undirected(), weight='weight')
                        # Convert list of sets to list of sorted lists for display
                        community_results = [sorted(list(c)) for c in communities_generator]
                        # Sort communities by size (largest first) for display
                        community_results.sort(key=len, reverse=True)
                        print(f"Found {len(community_results)} communities.")
                    except Exception as e_comm:
                         print(f"Error calculating communities: {e_comm}")
                         # Handle error, maybe pass an empty list or error message
                         community_results = [] # Or pass error message to template


        except Exception as e:
            error_message = f"Error during network analysis: {e}\n{traceback.format_exc()}"
            print(error_message)

    return render_template('network_results.html',
                           results=centrality_results,
                           communities=community_results, # Pass communities to template
                           graph_info=graph_info,
                           error=error_message)
    

@app.route('/clusters')
def clusters():
    error_message = None
    community_results = []  # List to hold communities
    graph_info = {}  # Dictionary for basic graph info

    if db is None:
        error_message = "Database connection not available."
    else:
        try:
            print("Fetching data for cluster analysis...")
            # Query to filter data from the database
            query = {
                "partner": {"$ne": "World"}, "reporter": {"$ne": "World"},
                "flow": "Export", "value": {"$gt": 0}
            }
            projection = {"_id": 0, "reporter": 1, "partner": 1, "value": 1}
            trade_data = list(db.trade_records.find(query, projection))

            if not trade_data:
                error_message = "No suitable trade data found in database to build network (check filters)."
            else:
                print(f"Building network graph from {len(trade_data)} export records...")
                G = nx.DiGraph()  # Directed graph
                for record in trade_data:
                    G.add_edge(record['reporter'], record['partner'], weight=record['value'])

                # Ensure the graph is not empty
                if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
                    error_message = "Graph could not be built (no valid nodes/edges)."
                else:
                    print(f"Graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
                    graph_info['nodes'] = G.number_of_nodes()
                    graph_info['edges'] = G.number_of_edges()

                    # --- Calculate Communities (Louvain) ---
                    print("Calculating Communities (Louvain method)...")
                    try:
                        communities_generator = nx_community.louvain_communities(
                            G.to_undirected(), weight='weight'
                        )
                        # Convert list of sets to list of sorted lists for display
                        community_results = [sorted(list(c)) for c in communities_generator]
                        # Sort communities by size (largest first)
                        community_results.sort(key=len, reverse=True)
                        print(f"Found {len(community_results)} communities.")
                    except Exception as e_comm:
                        print(f"Error calculating communities: {e_comm}")
                        community_results = []  # If there is an error, pass an empty list

        except Exception as e:
            error_message = f"Error during cluster analysis: {e}\n{traceback.format_exc()}"
            print(error_message)

    # Render the clusters page
    return render_template(
        'clusters.html',
        communities=community_results,
        graph_info=graph_info,
        error=error_message
    )



# Run the app if this script is executed directly
if __name__ == '__main__':
    print("Starting Flask application...")
    app.run(debug=True)
