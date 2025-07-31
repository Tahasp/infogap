import click
import os
import re
import requests
import tqdm
import dill
from wikidata.client import Client
from functools import partial
import pywikibot
import requests
import pandas as pd
import ipdb
import polars as pl
from collections import OrderedDict
from typing import Optional, List, Tuple, Iterable
from functools import partial
import loguru
import unicodedata
import urllib.parse

from flowmason.flowmason import conduct, load_artifact, load_artifact_with_step_name, SingletonStep

import loguru
from packages.steps.info_diff_steps import step_retrieve_en_content_blocks,\
    step_retrieve_fr_content_blocks, step_retrieve_zh_content_blocks, step_retrieve_ru_content_blocks, step_retrieve_prescraped_en_content_blocks
from packages.constants import BIO_SAVE_DIR, SCRATCH_DIR
from wikigap_topics_scrape import selected_topics
from wiki_text_process_test.examine_cache import examine_cache

logger = loguru.logger


def get_wikidata_id(topic, lang, **kwargs):
    """Fetches the Wikidata Item ID for a given Wikipedia article title."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&sites={lang}wiki&titles={topic}&props=info&format=json"
    response = requests.get(url)
    data = response.json()
    entities = data.get("entities", {})
    if entities:
        return list(entities.keys())[0]  # Return the first Wikidata ID found
    else: 
        logger.error(f"Could not find Wikidata ID for the given topic {topic}")
        return None

def get_interlanguage_links(wikidata_id, **kwargs):
    """Fetches interlanguage Wikipedia links for a given Wikidata Item ID."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wikidata_id}&props=sitelinks/urls&format=json"
    response = requests.get(url)
    data = response.json()
    sitelinks = data.get("entities", {}).get(wikidata_id, {}).get("sitelinks", {})
    # logger.info(f"Extracted sitelinks: {sitelinks}")
    language_links = {site: details['url'] for site, details in sitelinks.items()}
    return language_links

def extract_article_title_from_urls(urls, lang, **kwargs):
    lang_wiki = f"{lang}wiki"
    url = urls[lang_wiki]
    """Extracts the article title from a Wikipedia URL."""
    match = re.search(r"wiki/([^#?]*)", url)
    if match:
        return match.group(1).replace("_", " ")
    else: 
        print(url)
        logger.error(f"Can't extract title for url: {url}")
        
    return None

def get_wikipedia_text(article_title, lang, **kwargs):
    """Fetches all text content from a Wikipedia article."""
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&format=json&titles={article_title}"
    response = requests.get(url)
    data = response.json()
    
    pages = data.get("query", {}).get("pages", {})
    for page_id, page_data in pages.items():
        if "extract" in page_data:
            return page_data["extract"]
        else:
            logger.error(f"Could not find extract for title: {article_title}")
            return None

def make_lang_article_dict(en_article_title, en_lang, tgt_article_title, tgt_lang, **kwargs):
    # ipdb.set_trace()
    return {en_lang: en_article_title, tgt_lang: tgt_article_title}

def clean_text(text):
    # Remove unwanted Unicode control characters (invisible formatting marks)
    text = re.sub(r'[\u200f\u200e\u200d\u202c\u202d\u202e\u2066\u2067\u2068\u2069]', '', text)
    
    # Normalize Unicode (e.g., convert é → é in a consistent form)
    text = unicodedata.normalize('NFKC', text)
    
    # Remove non-printable characters but KEEP multilingual characters
    text = re.sub(r'[^\x20-\x7E\u00A0-\uFFFF]', '', text)  # Keeps Unicode text

    return text
    
def process_wikipedia_text(text, lang, **kwargs):
    ignore_headers = {
        "en": ["see also", "references", "external links"],
        "zh": ["参见", "参考资料", "参考文献", "外部链接"],
        "fr": ["voir aussi", "références"],
        "ru": ["см. также", "литература"],
        "ko": ["같이 보기", "참고 자료", "외부 링크"],
        "ja": ["関連項目", "参考文献", "外部リンク"],
        "he": ["מפיד", "הערות שוליים", "קישורים חיצוניים"],
        "bn": ["আরও দেখুন", "তথ্যসূত্র", "বহিঃসংযোগ"]
    }
    
    lines = text.split('\n')  # Split by new line
    processed_paragraphs = []
    
    for line in lines:
        line = line.strip()
        
        # Detect headers using regex
        header_match = re.match(r'^(=+)(.*?)\1$', line)
        if header_match:
            level = len(header_match.group(1)) - 1  # Count number of '=' to determine header level
            header_text = header_match.group(2).strip().lower()
            
            # If the detected header is in the ignore list, stop processing
            if lang in ignore_headers and header_text in ignore_headers[lang]:
                break  
            
            processed_paragraphs.append({f"header_{level}": header_text})  # Store header with level
            continue
        
        # Store paragraph if it meets length requirement
        elif len(line) >= 6:
            line = clean_text(line)
            processed_paragraphs.append({"paragraph": line})

    
    return processed_paragraphs

def step_load_both_bios(lang_article_dict, **kwargs):
    # create BIO_SAVE_DIR if it doesn't exist
    try:
        os.makedirs(BIO_SAVE_DIR)
    except FileExistsError:
        pass
    progress = tqdm.tqdm(total=len(lang_article_dict))
    failed_bio_ids = []
    for lang, article_title in lang_article_dict.items():
        logger.info(f"Retrieving content blocks for {lang} {article_title}")
        text = get_wikipedia_text(article_title, lang)
        logger.info(f"Successfully retrieved {len(text)} paragraphs for {lang} {article_title}")
        # Perform text processing on the retrieved blocks
        blocks = process_wikipedia_text(text, lang)
        decoded_article_title = urllib.parse.unquote(article_title)
        with open(f'{BIO_SAVE_DIR}/{decoded_article_title}_{lang}.pkl', 'wb') as f:
            dill.dump(blocks, f)
        logger.info(f"Saved content blocks for {lang} {decoded_article_title}")
    progress.update(1)
    logger.info(f"The failed bio ids are: {failed_bio_ids}")


@click.command()
def scrape_bios():
    tgt_lang = input("Enter the target language code you would like to scrape for these topics: ")
    lang = "en"
    en_tgt_title_pairs = []

    for topic in selected_topics:
        print(f"Processing topic: {topic}")
        step_dict = OrderedDict()
        step_dict['get_wikidata_id'] = SingletonStep(get_wikidata_id, {
            'topic': topic,
            'lang': lang,
            'version': '001'
        })
        step_dict['get_interlanguage_links'] = SingletonStep(get_interlanguage_links, {
            'wikidata_id': 'get_wikidata_id',
            'version': '001'
        })
        step_dict['extract_en_article_title_from_url'] = SingletonStep(extract_article_title_from_urls, {
            'urls': 'get_interlanguage_links',
            'lang': 'en',
            'version': '001'
        })
        step_dict['extract_tgt_article_title_from_url'] = SingletonStep(extract_article_title_from_urls, {
            'urls': 'get_interlanguage_links',
            'lang': tgt_lang,
            'version': '001'
        })
        step_dict['lang_article_dict'] = SingletonStep(make_lang_article_dict, {
            'en_article_title': 'extract_en_article_title_from_url',
            'en_lang': 'en',
            'tgt_article_title': 'extract_tgt_article_title_from_url',
            'tgt_lang': tgt_lang,
            'version': '001'
        })
        step_dict['step_load_both_bios'] = SingletonStep(step_load_both_bios, {
            'lang_article_dict': 'lang_article_dict',
            'version': '001'
        })
        metadata = conduct(
            os.path.join(SCRATCH_DIR, "bio_scrape_cache"),
            step_dict,
            f"new_scrape_en_{tgt_lang}_bios_{topic.replace(' ', '_')}"
        )
        cache_path_src_title = metadata[2][1]['cache_path']
        cache_path_tgt_title = metadata[3][1]['cache_path']
        
        src_title = examine_cache(cache_path_src_title)
        decoded_src_title = urllib.parse.unquote(src_title)
        tgt_title = examine_cache(cache_path_tgt_title)
        decoded_tgt_title = urllib.parse.unquote(tgt_title)
        en_tgt_title_pairs.append((decoded_src_title, decoded_tgt_title))
    
    output_path = f"packages/scraped_titles_{tgt_lang}.py"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Auto-generated file containing (English, Target language) topic tuples\n\n")
        f.write("en_tgt_title_pairs = [\n")
        for en, tgt in en_tgt_title_pairs:
            f.write(f"    ({repr(en)}, {repr(tgt)}),\n")
        f.write("]\n")

    print(f"\n✅ Saved {len(en_tgt_title_pairs)} topic pairs to {output_path}")


@click.group()
def main():
    pass

# main.add_command(scrape_french_bios_lgbtbiocorpus) # for replicating EMNLP'24
# main.add_command(scrape_russian_bios_lgbtbiocorpus) # for replicating EMNLP'24
# main.add_command(scrape_people_categories) # covariates for regression analysis in EMNLP'24
# main.add_command(scrape_ablation_bios)
# main.add_command(scrape_en_fr_bios)
# main.add_command(scrape_en_zh_bios) 

# for CSCW'26 WikiGap
main.add_command(scrape_bios)


if __name__ == '__main__':
    main()
    # bio_frame = load_artifact_with_step_name(metadata, "step_load_pairs_common")
    # bio_ids = load_bios()
    # extract_bios_en_fr(bio_ids)