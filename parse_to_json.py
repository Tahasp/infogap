import pandas as pd
import json
import argparse
import os
import glob
import ast
import requests
import re


SRC_LANGUAGE_FILTER = 'en'  # Replace 'en' with your desired language to filter out
    
def safe_value(value):
    """ Convert NaN to None (null in JSON) """
    return None if pd.isna(value) else value

def parse_as_list(value):
    """
    Try to ensure 'value' ends up as a Python list of strings.
    - If it's NaN or None, return None.
    - If it's already a list, return as-is.
    - If it's a string that looks like a Python list, use literal_eval().
    - Otherwise, just treat it as a single string item in a list.
    """
    if pd.isna(value):
        return None  # stay as null/None in JSON

    if isinstance(value, list):
        # It's already a list. Just return it as is.
        return value

    if isinstance(value, str):
        # Attempt to parse Python-style list, e.g. "['foo', 'bar']"
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
            else:
                # If it’s not a list, force it into one
                return [str(parsed)]
        except (SyntaxError, ValueError):
            # If it fails to parse, just put the entire string in a single-item array
            return [value]

    # If it’s some other type (like int, float, etc.), force to string in a single-item array
    return [str(value)]


def get_wikidata_id(article_title, lang='en'):
    """Fetches the Wikidata Item ID for a given Wikipedia article title."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&sites={lang}wiki&titles={article_title}&props=info&format=json"
    response = requests.get(url)
    data = response.json()
    
    entities = data.get("entities", {})
    if entities:
        return list(entities.keys())[0]  # Return the first Wikidata ID found
    return None

def get_interlanguage_links(wikidata_id):
    """Fetches interlanguage Wikipedia links for a given Wikidata Item ID."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wikidata_id}&props=sitelinks/urls&format=json"
    response = requests.get(url)
    data = response.json()
    
    sitelinks = data.get("entities", {}).get(wikidata_id, {}).get("sitelinks", {})
    language_links = {site: details['url'] for site, details in sitelinks.items()}
    return language_links

def get_tgt_wiki_link(name, src_lang, tgt_lang):
    """Get a target-language Wikipedia link via Wikidata."""
    topic = name
    lang = src_lang
    wikidata_id = get_wikidata_id(topic, lang)
    if not wikidata_id:
        print("Could not find Wikidata ID for the given topic.")
        return topic  # fallback: just return original name
    print(f"Wikidata ID for '{topic}': {wikidata_id}")
    
    tgt_lang_wiki = f"{tgt_lang}wiki"
    print(f"Fetching content for: {topic} in {tgt_lang_wiki}")
    interlanguage_links = get_interlanguage_links(wikidata_id)
    if tgt_lang_wiki in interlanguage_links:
        return interlanguage_links[tgt_lang_wiki]
    else:
        return topic

def df_to_nested_json(df):
    nested_dict = {}
    person = df['person_name'].values[0]
    languages = df['language'][df['language'] != SRC_LANGUAGE_FILTER].unique()
    # Pre-fetch the target wiki links for all languages
    languages_dict = {lang: get_tgt_wiki_link(person, SRC_LANGUAGE_FILTER, lang) for lang in languages}

    for _, row in df.iterrows():
        if row['language'] == SRC_LANGUAGE_FILTER:
            continue
        
        person = row['person_name']
        language = row['language']    
        tgt_wiki_link = languages_dict[language]
        header_1 = row['header_1'] if pd.notna(row['header_1']) else "General description"

        # Ensure structure
        nested_dict.setdefault(person, {})\
                   .setdefault('languages', {})\
                   .setdefault(language, {})\
                   .setdefault('headers', {})\
                   .setdefault(header_1, {'entries': []})

        # Convert 'tgt_fact_aligned_sentences' into a proper JSON array
        src_context = parse_as_list(row['src_context'])
        tgt_sentences = parse_as_list(row['tgt_fact_aligned_sentences'])

        nested_dict[person]['languages'][language]['headers'][header_1]['entries'].append({
            'header_2': {
                'original': safe_value(row['header_2']),
                'translated': safe_value(row['header_2_translated'])
            },
            'header_1': {
                'original': header_1,
                'translated': safe_value(row['header_1_translated'])
            },
            'fact': {
                'original': safe_value(row['fact']),
                'translated': safe_value(row['fact_translated']),
                'fact_aligned_sentence': safe_value(row['fact_aligned_sentence']),
                'wiki_link': tgt_wiki_link
            },
            'src_context': src_context,
            # Here we store real arrays, e.g.: ["sentence1", "sentence2"]
            'tgt_fact_aligned_sentences': tgt_sentences
        })

    return nested_dict

def main():
    """
    Reads the input CSV(s), performs a weighted sample in each DataFrame
    based on paragraph_index frequency, processes into nested JSON, and saves it.
    """
    from packages.scraped_titles_ru import en_tgt_title_pairs
    
    for (en_title, tgt_title) in en_tgt_title_pairs:
        topic = en_title
        print(f"Processing topic: {topic}")
        output_json = f"/Users/anniewang/Desktop/infogap/scratch/ethics_annotation_save/wikigap_data/json/{topic}.json"
        directory = f"/Users/anniewang/Desktop/infogap/scratch/ethics_annotation_save/wikigap_data/csv"
        file_pattern = os.path.join(directory, f"{topic}_*.csv")
        csv_files = glob.glob(file_pattern)

        if not csv_files:
            print(f"No files found for topic '{topic}' in directory '{directory}'.")
            return None

        dataframes = []
        sample_size = 10  # <--- Adjust this to however many rows you want to sample per CSV
        
        # Read each CSV, sample rows, store in dataframes
        for file in csv_files:
            print(file)
            df_temp = pd.read_csv(file)
            df_temp = df_temp[df_temp['language'] != SRC_LANGUAGE_FILTER]
            
            # --- Do some further processing for each dataframe: ---
            # Weighted sampling by paragraph_index frequency:
            if 'header_1' in df_temp.columns:
                freq = df_temp['header_1'].value_counts(normalize=True, dropna=False)
                print(freq)
                # Create a probability weight column for each row
                weights = df_temp['header_1'].map(freq)

                # Sample n rows (or len(df_temp) if it is smaller than n)
                df_temp = df_temp.sample(
                    n=min(sample_size, len(df_temp)), 
                    weights=weights, 
                    random_state=42
                )
            # ------------------------------------------------------

            dataframes.append(df_temp)

        # Concatenate all processed (sampled) DataFrames
        df = pd.concat(dataframes, ignore_index=True)

        # Convert DataFrame to JSON
        nested_json = df_to_nested_json(df)

        # Save to JSON file
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(nested_json, f, indent=4, ensure_ascii=False)

        print(f"JSON file saved successfully: {output_json}")

if __name__ == "__main__":
    # parser = argparse.ArgumentParser(
    #     description="Convert CSV file(s) to a nested JSON structure, with weighted sampling."
    # )
    # parser.add_argument("topic", help="topic_en")
    # args = parser.parse_args()
    # main(args.topics)
    main()