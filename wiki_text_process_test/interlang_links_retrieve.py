import requests
import json
import re

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

def extract_title_from_url(url):
    """Extracts the article title from a Wikipedia URL."""
    match = re.search(r"wiki/([^#?]*)", url)
    if match:
        return match.group(1).replace("_", " ")
    return None

def get_wikipedia_text(article_title, lang):
    """Fetches all text content from a Wikipedia article."""
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&format=json&titles={article_title}"
    print(url)
    response = requests.get(url)
    data = response.json()
    
    pages = data.get("query", {}).get("pages", {})
    for page_id, page_data in pages.items():
        if "extract" in page_data:
            return page_data["extract"]
    return "No content found."

def main():
    # Specify topic and language, and first find its Wikidata ID
    topic = input("Enter Wikipedia article title (e.g., Albert Einstein): ")
    lang = input("Enter Wikipedia language code (default: en): ") or "en"
    wikidata_id = get_wikidata_id(topic, lang)
    if not wikidata_id:
        print("Could not find Wikidata ID for the given topic.")
        return
    print(f"Wikidata ID for '{topic}': {wikidata_id}")
    
    # specify target language which you want to retireve the corresponding Wikipedia page
    tgt_lang = input("Enter target Wikipedia language code (default: fr): ") or "fr"
    tgt_lang_wiki = f"{tgt_lang}wiki"
    print(f"Fetching content for: {topic} in {tgt_lang_wiki}")
    interlanguage_links = get_interlanguage_links(wikidata_id)
    if interlanguage_links[tgt_lang_wiki]:
        print(f"Found Wikipedia article title: {interlanguage_links[tgt_lang_wiki]}")
        article_title = extract_title_from_url(interlanguage_links[tgt_lang_wiki])
        content = get_wikipedia_text(article_title, tgt_lang) 
        print("\nExtracted Wikipedia Content:\n")
        print(content, "...")  # Print only first 1000 characters for preview
        

if __name__ == "__main__":
    main()
