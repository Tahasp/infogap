import pickle
import dill
import sys

def inspect_pkl(file_path):
    """
    Inspect the contents of a .pkl file, including custom objects like Paragraph.
    
    Args:
        file_path (str): Path to the .pkl file.
    """
    try:
        # Try loading with pickle
        with open(file_path, 'rb') as file:
            data = pickle.load(file)
        print(f"Successfully loaded with pickle!")
    except Exception as e1:
        print(f"Failed with pickle: {e1}")
        try:
            # If pickle fails, try loading with dill
            with open(file_path, 'rb') as file:
                data = dill.load(file)
            print(f"Successfully loaded with dill!")
        except Exception as e2:
            print(f"Failed with dill: {e2}")
            return
    
    # Inspect the loaded data
    print("\n--- File Content Inspection ---")
    print(f"Type of the data: {type(data)}")
    if isinstance(data, list):
        print(f"Length: {len(data)}")
        if data and hasattr(data[0], "__dict__"):
            print("First 5 items (as dictionaries):")
            for i, item in enumerate(data[:5]):
                print(f"\nItem {i+1}:")
                print(item.__dict__)  # Display attributes of the object
        else:
            print("First 5 items:")
            print(data[:5])
    elif isinstance(data, dict):
        print(f"Keys: {list(data.keys())[:10]}")  # Show first 10 keys
        print(f"Length: {len(data)}")
    elif hasattr(data, "head") and callable(getattr(data, "head")):
        print("This is a DataFrame-like object. Displaying the first few rows:")
        print(data.head())
    else:
        print("Raw content:")
        print(data)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_pkl.py <path_to_pkl_file>")
    else:
        file_path = sys.argv[1]
        inspect_pkl(file_path)