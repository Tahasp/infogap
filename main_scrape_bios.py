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

from wikipedia_edit_scrape_tool import get_multilingual_wikilinks_mediawiki, Paragraph, DisambiguationPageError, Header, get_category
from flowmason.flowmason import conduct, load_artifact, load_artifact_with_step_name, SingletonStep

import loguru
from packages.steps.info_diff_steps import step_retrieve_en_content_blocks,\
    step_retrieve_fr_content_blocks, step_retrieve_zh_content_blocks, step_retrieve_ru_content_blocks, step_retrieve_prescraped_en_content_blocks
from packages.constants import BIO_SAVE_DIR, SCRATCH_DIR

logger = loguru.logger

def _get_frwiki_id(en_bio_id: str, progress: Optional[tqdm.tqdm] = None) -> str:
    wikilinks_dict = get_multilingual_wikilinks_mediawiki(en_bio_id)
    if progress:
        progress.update(1)
    if 'frwiki' in wikilinks_dict:
        return os.path.basename(wikilinks_dict['frwiki'])
    else:
        return 'unavailable through mediawiki'

def _get_ruwiki_id(en_bio_id: str) -> str:
    wikilinks_dict = get_multilingual_wikilinks_mediawiki(en_bio_id)
    if 'ruwiki' in wikilinks_dict:
        return os.path.basename(wikilinks_dict['ruwiki'])
    else:
        return 'unavailable through mediawiki'

def _get_zhwiki_id(en_bio_id: str, progress: Optional[tqdm.tqdm] = None) -> str:
    try:
        wikilinks_dict = get_multilingual_wikilinks_mediawiki(en_bio_id)
        if progress:
            progress.update(1)
        if 'zhwiki' in wikilinks_dict:
            return os.path.basename(wikilinks_dict['zhwiki'])
        else:
            return 'unavailable through mediawiki'
    except Exception as e:
        logger.error(f"Error in _get_zhwiki_id for {en_bio_id}: {e}")
        return 'error'

# TODO: make this a step, since it's a fairly long computation
def step_load_pairs_common(**kwargs) -> pl.DataFrame:
    target_person_name = []
    matched_person_name = []
    matched_categories = []
    with open('lgbt_bio_corpus.tsv', 'r') as f:
        for line in f:
            line_split = line.split('\t')
            target_en_bio, matched_en_bio = line_split[1], line_split[2]
            categories = line_split[3:]
            # target, matched, categories = line.split('\t')
            target_person_name.append(target_en_bio)
            matched_person_name.append(matched_en_bio)
            matched_categories.append(categories)
    frame = pl.DataFrame({
        'target_en_bio_id': target_person_name,
        'matched_en_bio_id': matched_person_name,
        'matched_categories': matched_categories
    })
    # add 'target_fr_bio_id' and 'matched_fr_bio_id' columns by using get_multilingual_wikilinks_mediawiki
    # that function takes an en_bio_id and returns a dictionary containing the pages for es, fr, ko, ru
    # we can then add the fr pages to the frame by getting os.path.basename(pages['frwiki'])
    # and adding that to the frame
    progress = tqdm.tqdm(total=len(frame))
    get_fr_wikiid_progress = partial(_get_frwiki_id, progress=progress)
    frame = frame.with_columns([
        pl.col('target_en_bio_id').map_elements(get_fr_wikiid_progress).alias('target_fr_bio_id'),
        pl.col('matched_en_bio_id').map_elements(_get_frwiki_id).alias('matched_fr_bio_id')
    ])
    return frame

def step_get_ru_pairs_common(**kwargs):
    target_person_en_ids= []
    matched_person_en_ids= []
    target_person_ru_ids = []
    matched_person_ru_ids = []
    count = 0
    with open("lgbt_bio_corpus.tsv", "r") as f:
        for line in f:
            line_split = line.split('\t')
            target_en_id, matched_en_id = line_split[1], line_split[2]
            target_person_en_ids.append(target_en_id)
            matched_person_en_ids.append(matched_en_id)
            target_ru_id = _get_ruwiki_id(target_en_id)
            matched_ru_id = _get_ruwiki_id(matched_en_id)
            target_person_ru_ids.append(target_ru_id)
            matched_person_ru_ids.append(matched_ru_id)
            count += 1
            if count % 100 == 0:
                logger.info(f"Processed {count} pairs.")
    frame = pl.DataFrame({
        'target_en_bio_id': target_person_en_ids,
        'matched_en_bio_id': matched_person_en_ids,
        'target_ru_bio_id': target_person_ru_ids,
        'matched_ru_bio_id': matched_person_ru_ids
    })
    return frame

def get_wikidata_id_from_page_id(page_id):
    # url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&prop=pageprops&pageids={page_id}"
    url = f"https://en.wikipedia.org/w/api.php?action=query&prop=pageprops&titles={page_id}&format=json"
    response = requests.get(url)
    data = response.json()
    pageid = list(data['query']['pages'].keys())[0]
    wikidata_id = data['query']['pages'][pageid]['pageprops']['wikibase_item']
    # Extracting the Wikidata ID from the response
    return wikidata_id

def get_ru_wikidata_id_from_page_id(page_id):
    url = f"https://ru.wikipedia.org/w/api.php?action=query&prop=pageprops&titles={page_id}&format=json"
    response = requests.get(url)
    data = response.json()
    pageid = list(data['query']['pages'].keys())[0]
    wikidata_id = data['query']['pages'][pageid]['pageprops']['wikibase_item']
    # Extracting the Wikidata ID from the response
    return wikidata_id

def _get_name(progress, client, en_bio_id):
    try:
        wikidata_id = get_wikidata_id_from_page_id(en_bio_id)
        entity = client.get(wikidata_id, load=True)
        # get the name of the person
        name = str(entity.label)
        assert name is not None
        progress.update(1)
    except KeyError:
        logger.warning(f"Could not find a wikidata id for {en_bio_id}")
        return 'unavailable through wikidata'
    return name 


def step_add_person_name_column_lgbt_bio_corpus(bio_frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    progress = tqdm.tqdm(total=len(bio_frame) * 2)
    get_name = partial(_get_name, progress=progress, client=Client())
    bio_frame = bio_frame.with_columns([
        pl.col('target_en_bio_id').map_elements(lambda element: get_name(en_bio_id=element)).alias('target_person_name'),
    ]).with_columns([
        pl.col('matched_en_bio_id').map_elements(lambda element: get_name(en_bio_id=element)).alias('matched_person_name')
    ])
    # log the number of rows that are null 
    logger.info(f"Number of rows with null target_person_name: {len(bio_frame.filter(pl.col('target_person_name').is_null()))}")
    return bio_frame

def step_add_person_name_column(bio_frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    progress = tqdm.tqdm(total=len(bio_frame))
    get_name = partial(_get_name, progress=progress, client=Client())
    bio_frame = bio_frame.with_columns([
        pl.col('en_bio_id').map_elements(lambda element: get_name(en_bio_id=element)).alias('person_name'),
    ])
    # log the number of rows that are null 
    logger.info(f"Number of rows with null target_person_name: {len(bio_frame.filter(pl.col('person_name').is_null()))}")
    return bio_frame


def step_load_ru_bios(en_ru_bio_id_names: List[Tuple[str,str,str, str]], **kwargs):
    en_bio_ids = [en_bio_id for en_bio_id, _, _,_ in en_ru_bio_id_names]
    ru_bio_ids = [ru_bio_id for _, ru_bio_id, _,_ in en_ru_bio_id_names]
    # create BIO_SAVE_DIR if it doesn't exist
    try:
        os.makedirs(BIO_SAVE_DIR)
    except FileExistsError:
        pass
    progress = tqdm.tqdm(total=len(en_bio_ids))

    failed_bio_ids = []
    for i in range(len(en_bio_ids)):
        en_bio_id = en_bio_ids[i]
        ru_bio_id = ru_bio_ids[i]
        # check if the bio_id has already been processed. TODO: UNCOMMENT LATER
        if os.path.exists(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl') and os.path.exists(f'{BIO_SAVE_DIR}/{ru_bio_id}_ru.pkl'):
            progress.update(1)
            continue
        try:
            en_blocks = step_retrieve_en_content_blocks(en_bio_id)
            ru_blocks = step_retrieve_ru_content_blocks(ru_bio_id)
            if not os.path.exists(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl'): 
                with open(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl', 'wb') as f:
                    dill.dump(en_blocks, f)
            if not os.path.exists(f'{BIO_SAVE_DIR}/{ru_bio_id}_ru.pkl'):
                with open(f'{BIO_SAVE_DIR}/{ru_bio_id}_ru.pkl', 'wb') as f:
                    dill.dump(ru_blocks, f)
        except DisambiguationPageError: 
            logger.error(f"Failed on {en_bio_id} as it is a disambiguation page.")
            failed_bio_ids.append(en_bio_id)
            # raise Exception(f"Failed on {en_bio_id}")
        except:
            logger.error(f"Failed on {en_bio_id}")
            failed_bio_ids.append(en_bio_id)
            continue
            # raise Exception(f"Failed on {en_bio_id}")
        progress.update(1)
    logger.info(f"The failed bio ids are: {failed_bio_ids}")


def step_load_bios(en_fr_bio_ids_names: List[Tuple[str,str]], **kwargs):
    logger.info(f"Processing bio IDs: {en_fr_bio_ids_names}")
    en_bio_ids = [en_bio_id for en_bio_id, _, _ in en_fr_bio_ids_names]
    fr_bio_ids = [fr_bio_id for _, fr_bio_id, _ in en_fr_bio_ids_names]
    # create BIO_SAVE_DIR if it doesn't exist
    try:
        os.makedirs(BIO_SAVE_DIR)
    except FileExistsError:
        pass
    progress = tqdm.tqdm(total=len(en_bio_ids))

    failed_bio_ids = []
    for i in range(len(en_bio_ids)):
        en_bio_id = en_bio_ids[i]
        fr_bio_id = fr_bio_ids[i]

        # check if the bio_id has already been processed. TODO: UNCOMMENT LATER
        if os.path.exists(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl') and os.path.exists(f'{BIO_SAVE_DIR}/{fr_bio_id}_fr.pkl'):
            progress.update(1)
            continue
        try:
            logger.info(f"Retrieving content blocks for {en_bio_id} and {fr_bio_id}")
            en_blocks = step_retrieve_en_content_blocks(en_bio_id)
            logger.info(f"Successfully retrieved {len(en_blocks)} paragraphs for {en_bio_id}")
            with open(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl', 'wb') as f:
                dill.dump(en_blocks, f)
            logger.info(f"Saved content blocks for {en_bio_id}")

            fr_blocks = step_retrieve_fr_content_blocks(fr_bio_id)
            logger.info(f"Successfully retrieved {len(fr_blocks)} paragraphs for {fr_bio_id}")
            with open(f'{BIO_SAVE_DIR}/{fr_bio_id}_fr.pkl', 'wb') as f:
                dill.dump(fr_blocks, f)
            logger.info(f"Saved content blocks for {en_bio_id}")
        except DisambiguationPageError: 
            logger.error(f"Failed on {en_bio_id} as it is a disambiguation page.")
            failed_bio_ids.append(en_bio_id)
            # raise Exception(f"Failed on {en_bio_id}")
        except:
            logger.error(f"Failed on {en_bio_id}")
            failed_bio_ids.append(en_bio_id)
            continue
            # raise Exception(f"Failed on {en_bio_id}")
        progress.update(1)
    logger.info(f"The failed bio ids are: {failed_bio_ids}")



def step_load_zh_bios(en_zh_bio_ids_names: List[Tuple[str,str]], **kwargs):
    logger.info(f"Processing bio IDs: {en_zh_bio_ids_names}")
    en_bio_ids = [en_bio_id for en_bio_id, _, _ in en_zh_bio_ids_names]
    zh_bio_ids = [zh_bio_id for _, zh_bio_id, _ in en_zh_bio_ids_names]
    # create BIO_SAVE_DIR if it doesn't exist
    try:
        os.makedirs(BIO_SAVE_DIR)
    except FileExistsError:
        pass
    progress = tqdm.tqdm(total=len(en_bio_ids))

    failed_bio_ids = []
    for i in range(len(en_bio_ids)):
        en_bio_id = en_bio_ids[i]
        zh_bio_id = zh_bio_ids[i]

        # check if the bio_id has already been processed. TODO: UNCOMMENT LATER
        if os.path.exists(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl') and os.path.exists(f'{BIO_SAVE_DIR}/{zh_bio_id}_zh.pkl'):
            progress.update(1)
            continue
        try:
            logger.info(f"Retrieving content blocks for {en_bio_id} and {zh_bio_id}")
            en_blocks = step_retrieve_en_content_blocks(en_bio_id)
            logger.info(f"Successfully retrieved {len(en_blocks)} paragraphs for {en_bio_id}")
            with open(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl', 'wb') as f:
                dill.dump(en_blocks, f)
            logger.info(f"Saved content blocks for {en_bio_id}")

            zh_blocks = step_retrieve_zh_content_blocks(zh_bio_id)
            logger.info(f"Successfully retrieved {len(zh_blocks)} paragraphs for {zh_bio_id}")
            with open(f'{BIO_SAVE_DIR}/{zh_bio_id}_zh.pkl', 'wb') as f:
                dill.dump(zh_blocks, f)
            logger.info(f"Saved content blocks for {en_bio_id}")
        except DisambiguationPageError: 
            logger.error(f"Failed on {en_bio_id} as it is a disambiguation page.")
            failed_bio_ids.append(en_bio_id)
            # raise Exception(f"Failed on {en_bio_id}")
        except:
            logger.error(f"Failed on {en_bio_id}")
            failed_bio_ids.append(en_bio_id)
            continue
            # raise Exception(f"Failed on {en_bio_id}")
        progress.update(1)
    logger.info(f"The failed bio ids are: {failed_bio_ids}")




def step_load_zh_bios(en_zh_bio_ids_names: List[Tuple[str,str]], **kwargs):
    logger.info(f"Processing bio IDs: {en_zh_bio_ids_names}")
    en_bio_ids = [en_bio_id for en_bio_id, _, _ in en_zh_bio_ids_names]
    zh_bio_ids = [zh_bio_id for _, zh_bio_id, _ in en_zh_bio_ids_names]
    # create BIO_SAVE_DIR if it doesn't exist
    try:
        os.makedirs(BIO_SAVE_DIR)
    except FileExistsError:
        pass
    progress = tqdm.tqdm(total=len(en_bio_ids))

    failed_bio_ids = []
    for i in range(len(en_bio_ids)):
        en_bio_id = en_bio_ids[i]
        zh_bio_id = zh_bio_ids[i]

        # check if the bio_id has already been processed. TODO: UNCOMMENT LATER
        if os.path.exists(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl') and os.path.exists(f'{BIO_SAVE_DIR}/{zh_bio_id}_zh.pkl'):
            progress.update(1)
            continue
        try:
            logger.info(f"Retrieving content blocks for {en_bio_id} and {zh_bio_id}")
            en_blocks = step_retrieve_en_content_blocks(en_bio_id)
            logger.info(f"Successfully retrieved {len(en_blocks)} paragraphs for {en_bio_id}")
            with open(f'{BIO_SAVE_DIR}/{en_bio_id}_en.pkl', 'wb') as f:
                dill.dump(en_blocks, f)
            logger.info(f"Saved content blocks for {en_bio_id}")

            zh_blocks = step_retrieve_zh_content_blocks(zh_bio_id)
            logger.info(f"Successfully retrieved {len(zh_blocks)} paragraphs for {zh_bio_id}")
            with open(f'{BIO_SAVE_DIR}/{zh_bio_id}_zh.pkl', 'wb') as f:
                dill.dump(zh_blocks, f)
            logger.info(f"Saved content blocks for {en_bio_id}")
        except DisambiguationPageError: 
            logger.error(f"Failed on {en_bio_id} as it is a disambiguation page.")
            failed_bio_ids.append(en_bio_id)
            # raise Exception(f"Failed on {en_bio_id}")
        except:
            logger.error(f"Failed on {en_bio_id}")
            failed_bio_ids.append(en_bio_id)
            continue
            # raise Exception(f"Failed on {en_bio_id}")
        progress.update(1)
    logger.info(f"The failed bio ids are: {failed_bio_ids}")



def step_filter_rows(bio_frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    initial_size = len(bio_frame)
    bio_frame = bio_frame.filter(pl.col('fr_bio_id') != 'unavailable through mediawiki')
    bio_frame = bio_frame.filter(pl.col('person_name') != 'unavailable through wikidata')
    current_size = len(bio_frame)
    logger.info(f"Filtered out {initial_size - current_size} rows.")
    ipdb.set_trace()
    return bio_frame

def step_filter_rows_zh(bio_frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    try:
        logger.info(f"Columns in bio_frame before filtering: {bio_frame.columns}")
        initial_size = len(bio_frame)
        bio_frame = bio_frame.filter(pl.col('zh_bio_id') != 'unavailable through mediawiki')
        bio_frame = bio_frame.filter(pl.col('person_name') != 'unavailable through wikidata')
        current_size = len(bio_frame)
        logger.info(f"Filtered out {initial_size - current_size} rows.")
        return bio_frame
    except Exception as e:
        logger.error(f"Error in step_filter_rows_zh: {e}")
        raise

def step_filter_rows_lgbtbiocorpus(bio_frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    initial_size = len(bio_frame)
    bio_frame = bio_frame.filter(pl.col('target_fr_bio_id') != 'unavailable through mediawiki')
    bio_frame = bio_frame.filter(pl.col('matched_fr_bio_id') != 'unavailable through mediawiki')
    bio_frame = bio_frame.filter(pl.col('target_person_name') != 'unavailable through wikidata')
    current_size = len(bio_frame)
    logger.info(f"Filtered out {initial_size - current_size} rows.")
    return bio_frame

def step_obtain_target_en_fr_bio_ids_lgbtbiocorpus(bio_frame, **kwargs):
    # get the corresponding fr bio ids
    inital_target_en_bio_ids = bio_frame['target_en_bio_id'].to_list()
    target_fr_bio_ids = bio_frame['target_fr_bio_id'].to_list()
    person_names = bio_frame['target_person_name'].to_list()

    initial_control_en_bio_ids = bio_frame['matched_en_bio_id'].to_list()
    control_fr_bio_ids = bio_frame['matched_fr_bio_id'].to_list()
    control_person_names = bio_frame['matched_person_name'].to_list()
    # # zip the en and fr bio ids together
    en_fr_bio_ids_names = list(zip(inital_target_en_bio_ids + initial_control_en_bio_ids, 
                                   target_fr_bio_ids + control_fr_bio_ids, 
                                   person_names + control_person_names))
    return en_fr_bio_ids_names

def step_obtain_target_en_fr_bio_ids(bio_frame, **kwargs):
    # get the corresponding fr bio ids
    en_bio_ids = bio_frame['en_bio_id'].to_list()
    fr_bio_ids = bio_frame['fr_bio_id'].to_list()
    person_names = bio_frame['person_name'].to_list()

    # # zip the en and fr bio ids together
    en_fr_bio_ids_names = list(zip(en_bio_ids, 
                                   fr_bio_ids, 
                                   person_names ))
    logger.info(f"{en_fr_bio_ids_names}")

    
    return en_fr_bio_ids_names



def step_obtain_target_en_zh_bio_ids(bio_frame, **kwargs):
    # get the corresponding fr bio ids
    en_bio_ids = bio_frame['en_bio_id'].to_list()
    zh_bio_ids = bio_frame['zh_bio_id'].to_list()
    person_names = bio_frame['person_name'].to_list()

    # # zip the en and fr bio ids together
    en_zh_bio_ids_names = list(zip(en_bio_ids, 
                                   zh_bio_ids, 
                                   person_names ))
    logger.info(f"{en_zh_bio_ids_names}")

    
    return en_zh_bio_ids_names


def step_obtain_target_en_ru_bio_ids(bio_frame, **kwargs):
    ipdb.set_trace()

# def step_load_people_names(en_fr_bio_ids):
def step_log_ids_and_names(en_fr_bio_ids_names, **kwargs):
    en_bio_ids = [en_bio_id for en_bio_id, _, _ in en_fr_bio_ids_names]
    fr_bio_ids = [fr_bio_id for _, fr_bio_id, _ in en_fr_bio_ids_names]
    names = [name for _, _, name in en_fr_bio_ids_names]
    # save this to a csv file
    bio_id_name_frame = pl.DataFrame({
        'en_bio_id': en_bio_ids,
        'fr_bio_id': fr_bio_ids,
        'name': names
    })
    bio_id_name_frame.write_csv('bio_id_name.csv')


def get_ru_wikidata_id_from_page_id(page_id):
    url = f"https://ru.wikipedia.org/w/api.php?action=query&prop=pageprops&titles={page_id}&format=json"
    response = requests.get(url)
    data = response.json()
    pageid = list(data['query']['pages'].keys())[0]
    wikidata_id = data['query']['pages'][pageid]['pageprops']['wikibase_item']
    # Extracting the Wikidata ID from the response
    return wikidata_id

def get_ru_wikidata_id_from_page_id(page_id):
    url = f"https://ru.wikipedia.org/w/api.php?action=query&prop=pageprops&titles={page_id}&format=json"
    response = requests.get(url)
    data = response.json()
    pageid = list(data['query']['pages'].keys())[0]
    wikidata_id = data['query']['pages'][pageid]['pageprops']['wikibase_item']
    # Extracting the Wikidata ID from the response
    return wikidata_id

def step_add_ru_name_column(bio_frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    site = pywikibot.Site('wikipedia:ru')
    repo = site.data_repository()  # the Wikibase repository for given site
    ru_progress = tqdm.tqdm(total=len(bio_frame) * 2)
    def _get_name_ru(ru_bio_id):
        ru_progress.update(1)
        try:
            wikidata_id = get_ru_wikidata_id_from_page_id(ru_bio_id)
            page = repo.page_from_repository(wikidata_id)  # create a local page for the given item
            item = pywikibot.ItemPage(repo, wikidata_id)
            data = item.get()['labels']
            name = data['ru']
            return name
        except KeyError:
            return 'unavailable through wikidata'
        except ConnectionError:
            return 'unavailable through wikidata'

    bio_frame = bio_frame.with_columns([
        pl.col('target_ru_bio_id').map_elements(lambda element: _get_name_ru(element)).alias('target_ru_person_name'),
    ]).with_columns([
        pl.col('matched_ru_bio_id').map_elements(lambda element: _get_name_ru(element)).alias('matched_ru_person_name')
    ])    
    # en_progress = tqdm.tqdm(total=len(bio_frame) * 2)
    # get_name = partial(_get_name, progress=en_progress, client=Client())
    # bio_frame = bio_frame.with_columns([
    #     pl.col('target_en_bio_id').map_elements(lambda element: get_name(en_bio_id=element)).alias('target_person_en_name'),
    # ]).with_columns([
    #     pl.col('matched_en_bio_id').map_elements(lambda element: get_name(en_bio_id=element)).alias('matched_person_en_name')
    # ])
    return bio_frame

def step_add_en_name_column(bio_frame, **kwargs):
    with open(f"{SCRATCH_DIR}/bio_scrape_cache/e360b31630be521540de698e617098319f51b2b01216b6d43681481c9e625170", "rb") as f:
        en_fr_bio_frame = dill.load(f)
    
    # add the target_person_name and matched_person_name columns to the bio_frame
    bio_frame = bio_frame.join(en_fr_bio_frame.select(['target_en_bio_id', 'target_person_name']), on='target_en_bio_id', how='inner')
    bio_frame = bio_frame.join(en_fr_bio_frame.select(['matched_en_bio_id', 'matched_person_name']), on='matched_en_bio_id', how='inner')
    return bio_frame

def step_obtain_target_en_ru_bio_ids(bio_frame, **kwargs):
    bio_frame = bio_frame.unique('target_en_bio_id')
    bio_frame = bio_frame.filter((pl.col('target_ru_person_name') != 'unavailable through wikidata') & (pl.col('target_ru_bio_id') != 'unavailable through mediawiki') &\
                     (pl.col('matched_ru_person_name') != 'unavailable through wikidata') & (pl.col('matched_ru_bio_id') != 'unavailable through mediawiki') &\
                     (pl.col('target_person_name') != 'unavailable through wikidata')) 
    en_bio_ids = bio_frame['target_en_bio_id'].to_list() + bio_frame['matched_en_bio_id'].to_list()
    ru_bio_ids = bio_frame['target_ru_bio_id'].to_list() + bio_frame['matched_ru_bio_id'].to_list()
    en_names = bio_frame['target_person_name'].to_list() + bio_frame['matched_person_name'].to_list()
    ru_names = bio_frame['target_ru_person_name'].to_list() + bio_frame['matched_ru_person_name'].to_list()
    # there is a person missing from ru_bio_ids: "Соседов,_Сергей_Васильевич"

    # assert everything is the same length
    assert len(en_bio_ids) == len(ru_bio_ids) == len(en_names) == len(ru_names)
    logger.info(f"English bio ids: {en_bio_ids}")
    logger.info(f"Russian bio ids: {ru_bio_ids}")
    logger.info(f"English names: {en_names}")
    logger.info(f"Russian names: {ru_names}")
    return list(zip(en_bio_ids, ru_bio_ids, en_names, ru_names))

def step_log_ids_and_names_ru(en_ru_ids_names: List[Tuple[str,str,str,str]], **kwargs):
    en_bio_ids = []
    ru_bio_ids = []
    en_names, ru_names = [], []
    for profile in en_ru_ids_names:
        # check if {en_bio_id}_en.pkl and {ru_bio_id}_ru.pkl exist
        if os.path.exists(f'{BIO_SAVE_DIR}/{profile[0]}_en.pkl') and os.path.exists(f'{BIO_SAVE_DIR}/{profile[1]}_ru.pkl'):
            en_bio_ids.append(profile[0])
            ru_bio_ids.append(profile[1])
            en_names.append(profile[2])
            ru_names.append(profile[3])
        # en_bio_ids.append(profile[0])
        # ru_bio_ids.append(profile[1])
        # en_names.append(profile[2])
        # ru_names.append(profile[3])
    bio_id_name_frame = pl.DataFrame({
        'en_bio_id': en_bio_ids,
        'ru_bio_id': ru_bio_ids,
        'en_name': en_names,
        'ru_name': ru_names
    }).write_csv('bio_id_name_ru.tsv', separator='\t')

def step_load_en_section_headers(**kwargs):
    frame = pl.read_csv('bio_id_name.csv')
    en_bio_ids = frame['en_bio_id'].to_list()

    frames = []
    for bio in tqdm.tqdm(en_bio_ids):
        current_header = "ArticlePreamble"
        paragraph_index = 0
        sections = []
        paragraph_indices = []
        if not os.path.exists(f'{BIO_SAVE_DIR}/{bio}_en.pkl'):
            continue
        with open(f'{BIO_SAVE_DIR}/{bio}_en.pkl', 'rb') as f:
            en_blocks = dill.load(f)
        for block in en_blocks:
            if isinstance(block, Paragraph):
                sections.append(current_header)
                paragraph_indices.append(paragraph_index)
                paragraph_index += 1
            elif isinstance(block, Header) and block.level == 2 and block.text != "Contents":
                current_header = block.text
        frames.append(
            pl.DataFrame({
                'en_bio_id': [str(bio)] * len(paragraph_indices),
                'section_header': sections,
                'paragraph_index': paragraph_indices
            }).select(
                pl.col('en_bio_id').cast(str),
                pl.col('section_header').cast(str),
                pl.col('paragraph_index').cast(int)
            )
        )
    result = pl.concat(frames)
    return result

def step_load_fr_section_headers(**kwargs):
    frame = pl.read_csv('bio_id_name.csv')
    fr_bio_ids = frame['fr_bio_id'].to_list()

    frames = []
    for bio in tqdm.tqdm(fr_bio_ids):
        current_header = "ArticlePreamble"
        paragraph_index = 0
        sections = []
        paragraph_indices = []
        if not os.path.exists(f'{BIO_SAVE_DIR}/{bio}_fr.pkl'):
            continue
        with open(f'{BIO_SAVE_DIR}/{bio}_fr.pkl', 'rb') as f:
            en_blocks = dill.load(f)
        for block in en_blocks:
            if isinstance(block, Paragraph):
                sections.append(current_header)
                paragraph_indices.append(paragraph_index)
                paragraph_index += 1
            elif isinstance(block, Header) and block.level == 2 and block.text != "Sommaire":
                current_header = block.text
        frames.append(
            pl.DataFrame({
                'fr_bio_id': [str(bio)] * len(paragraph_indices),
                'section_header': sections,
                'paragraph_index': paragraph_indices
            }).select(
                pl.col('fr_bio_id').cast(str),
                pl.col('section_header').cast(str),
                pl.col('paragraph_index').cast(int)
            )
        )
    result = pl.concat(frames)
    return result

def step_load_ru_section_headers(**kwargs):
    frame = pl.read_csv('bio_id_name_ru.tsv', separator='\t')
    ru_bio_ids = frame['ru_bio_id'].to_list()

    frames = []
    for bio in tqdm.tqdm(ru_bio_ids):
        current_header = "ArticlePreamble"
        paragraph_index = 0
        sections = []
        paragraph_indices = []
        if not os.path.exists(f'{BIO_SAVE_DIR}/{bio}_ru.pkl'):
            continue
        with open(f'{BIO_SAVE_DIR}/{bio}_ru.pkl', 'rb') as f:
            ru_blocks = dill.load(f)
        for block in ru_blocks:
            if isinstance(block, Paragraph):
                sections.append(current_header)
                paragraph_indices.append(paragraph_index)
                paragraph_index += 1
            elif isinstance(block, Header) and block.level == 2 and block.text != "Содержание": 
                current_header = block.text
        frames.append(
            pl.DataFrame({
                'ru_bio_id': [str(bio)] * len(paragraph_indices),
                'section_header': sections,
                'paragraph_index': paragraph_indices
            }).select(
                pl.col('ru_bio_id').cast(str),
                pl.col('section_header').cast(str),
                pl.col('paragraph_index').cast(int)
            )
        )
    result = pl.concat(frames)
    return result

    # return pl.concat(frames)

@click.command()
def scrape_french_bios_lgbtbiocorpus():
    step_dict = OrderedDict()
    step_dict['step_load_pairs_common'] = SingletonStep(step_load_pairs_common, {
        'version': '001'
    })
    step_dict['step_add_person_name_column'] = SingletonStep(step_add_person_name_column_lgbt_bio_corpus, {
        'bio_frame': 'step_load_pairs_common',
        'version': '001'
    })
    step_dict['step_filter_rows'] = SingletonStep(step_filter_rows_lgbtbiocorpus, {
        'bio_frame': 'step_add_person_name_column', 
        'version': '001'
    })
    step_dict['step_obtain_target_en_fr_bio_ids'] = SingletonStep(step_obtain_target_en_fr_bio_ids_lgbtbiocorpus, {
        'bio_frame': 'step_filter_rows',
        'version': '007'
    })
    step_dict['step_load_bios'] = SingletonStep(step_load_bios, {
        'en_fr_bio_ids_names': 'step_obtain_target_en_fr_bio_ids',
        'version': '003'
    })
    step_dict['step_log_ids_and_names'] = SingletonStep(step_log_ids_and_names, {
        'en_fr_bio_ids_names': 'step_obtain_target_en_fr_bio_ids',
        'version': '001'
    })
    metadata = conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, "scrape_bios_log")


@click.command()
def scrape_russian_bios_lgbtbiocorpus():
    step_dict = OrderedDict()
    step_dict['step_load_russian_pairs_common'] = SingletonStep(step_get_ru_pairs_common, {
        'version': '001'
    })
    step_dict['step_add_ru_name_column'] = SingletonStep(step_add_ru_name_column, {
        'bio_frame': 'step_load_russian_pairs_common',
        'version': '002'
    })
    step_dict['step_add_en_name_column'] = SingletonStep(step_add_en_name_column, {
        'bio_frame': 'step_add_ru_name_column',
        'version': '002'
    })
    step_dict['step_obtain_target_en_ru_bio_ids'] = SingletonStep(step_obtain_target_en_ru_bio_ids, {
        'bio_frame': 'step_add_en_name_column',
        'version': '005'
    })
    step_dict['step_load_bios'] = SingletonStep(step_load_ru_bios, {
        'en_ru_bio_id_names': 'step_obtain_target_en_ru_bio_ids',
        'version': '001'
    })
    step_dict['step_log_ids_and_names'] = SingletonStep(step_log_ids_and_names_ru, {
        'en_ru_ids_names': 'step_obtain_target_en_ru_bio_ids',
        'version': '001'
    })
    step_dict['step_load_en_paragraph_section_headers'] = SingletonStep(step_load_en_section_headers, {
        'version': '002'
    })
    step_dict['step_load_fr_paragraph_section_headers'] = SingletonStep(step_load_fr_section_headers, {
        'version': '001'
    })
    step_dict['step_load_ru_paragraph_section_headers'] = SingletonStep(step_load_ru_section_headers, {
        'version': '004'
    })
    metadata = conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, "scrape_bios_log")

def step_scrape_all_categories(**kwargs):
    people_frame = pl.read_csv('bio_id_name.csv')
    en_bio_ids = people_frame['en_bio_id'].to_list()
    bio_ids = []
    all_categories = []
    for bio in tqdm.tqdm(en_bio_ids):
        categories = get_category(bio, 'enwiki')
        all_categories.append(categories)
        bio_ids.append(bio)
    frame = pl.DataFrame({
        'en_bio_id': bio_ids,
        'categories': all_categories
    })
    frame.write_json("people_categories.json")

def step_define_ethnicity(**kwargs):
    category_frame = pl.read_json("people_categories.json")
    def assign_ethnicity(category_list: List[str]) -> str:
        for category in category_list:
            if category.startswith('Category:Hispanic'):
                return 'Hispanic'
            if category.startswith('Category:African-American'):
                return 'Black'
            if category.startswith('Category:Asian-American') or \
                category.endswith('Asian descent'):
                return 'Asian'
            if category.startswith('Category:South Korean') or \
                category.startswith('Category:Japanese') or \
                category.startswith('Category:Chinese') or \
                category.startswith('Category:Vietnamese') or \
                category.startswith('Category:Filipino') or \
                category.startswith('Category:Thai') or \
                category.startswith('Category:Indonesian') or \
                category.startswith('Category:Malaysian') or \
                category.startswith('Category:Singaporean') or \
                category.startswith('Category:Bruneian') or \
                category.startswith('Category:Laotian') or \
                category.startswith('Category:Cambodian') or \
                category.startswith('Category:Myanmar') or \
                category.startswith('Category:Bangladeshi') or \
                category.startswith('Category:Nepalese') or \
                category.startswith('Category:Bhutanese') or \
                category.startswith('Category:Maldivian'):
                return 'East Asian' 
            if category.startswith('Category:Native American'):
                return 'Native American'
            if category.startswith('Category:Indian') or \
                category.startswith('Category:Pakistani') or \
                category.startswith('Category:Sri Lankan') or \
                category.startswith('Category:Sri Lankan') or \
                category.startswith('Category:Afghan') or \
                category.startswith('Category:Pakistani') or \
                category.startswith('Category:Indian') or \
                category.startswith('Category:Nepalese') or \
                category.startswith('Category:Bhutanese') or \
                category.startswith('Category:Maldivian') or \
                category.startswith('Category:Sri Lankan'):
                return 'South Asian'
            # add middle-eastern category
            if category.startswith('Category:Arab'):
                return 'Arab'
        return 'Unknown'
    category_frame = category_frame.with_columns([
        pl.col('categories').map_elements(assign_ethnicity)\
            .alias('ethnicity')
    ])
    category_frame.select('en_bio_id', 'ethnicity').write_csv("en_bio_id_ethnicity.csv")
    # return category_frame

@click.command()
def scrape_people_categories():
    step_dict = OrderedDict()
    # step_dict['step_scrape_all_categories'] = SingletonStep(step_load_pairs_common, {
    #     'version': '001'
    # })
    step_dict['step_define_ethnicity'] = SingletonStep(step_define_ethnicity, {
        'version': '002'
    })
    conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, "scrape_people_categories")


@click.command()
def scrape_ablation_bios():
    person_names = ['Sophie Labelle', 'Gabriel Attal', 'Caroline Mécary', 'Tim Cook', 'Ellen DeGeneres', 'Kim Petras', 'Alan Turing', 'Philippe Besson', 'Frédéric Mitterrand', 'Abdellah Taïa']
    en_bio_ids = ['Sophie_Labelle', 'Gabriel_Attal', 'Caroline_Mécary', 'Tim_Cook', 'Ellen_DeGeneres', 'Kim_Petras', 'Alan_Turing', 'Philippe_Besson', 'Frédéric_Mitterrand', 'Abdellah_Taïa']
    fr_bio_ids = ['Sophie_Labelle', 'Gabriel_Attal', 'Caroline_Mécary', 'Tim_Cook', 'Ellen_DeGeneres', 'Kim_Petras', 'Alan_Turing', 'Philippe_Besson', 'Frédéric_Mitterrand', 'Abdellah_Taïa']

    step_dict = OrderedDict()
    step_dict['step_load_bios'] = SingletonStep(step_load_bios, {
        'en_fr_bio_ids_names': tuple(zip(en_bio_ids, fr_bio_ids, person_names)),
        'version': '001'
    })
    # step_dict['step_log_ids_and_names'] = SingletonStep(step_log_ids_and_names, {
    #     'en_fr_bio_ids_names': 'step_load_bios',
    #     'version': '001'
    # })
    metadata = conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, "scrape_ablation_bios")

def step_get_en_fr_bio_ids(**kwargs) -> pl.DataFrame:
    try:
        en_bio_ids = ['Oolong','Mandarin_orange']
        frame = pl.DataFrame({
            'en_bio_id': en_bio_ids
        })
        progress = tqdm.tqdm(total=len(frame))
        get_fr_wikiid_progress = partial(_get_frwiki_id, progress=progress)
        frame = frame.with_columns([
            pl.col('en_bio_id').map_elements(get_fr_wikiid_progress).alias('fr_bio_id'),
        ])
        ipdb.set_trace()
    except Exception as e:
        print(e)
    return frame

@click.command()
def scrape_en_fr_bios():
    step_dict = OrderedDict()
    step_dict['step_get_id_frame'] = SingletonStep(step_get_en_fr_bio_ids, {
        'version': '001'
    })
    step_dict['step_add_person_name_column'] = SingletonStep(step_add_person_name_column, {
        'bio_frame': 'step_get_id_frame',
        'version': '001'
    })
    step_dict['step_filter_rows'] = SingletonStep(step_filter_rows, {
        'bio_frame': 'step_add_person_name_column', 
        'version': '001'
    })
    step_dict['step_obtain_target_en_fr_bio_ids'] = SingletonStep(step_obtain_target_en_fr_bio_ids, {
        'bio_frame': 'step_filter_rows',
        'version': '007'
    })
    step_dict['step_load_bios'] = SingletonStep(step_load_bios, {
        'en_fr_bio_ids_names': 'step_obtain_target_en_fr_bio_ids',
        'version': '001'
    })

    metadata = conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, "scrape_en_fr_bios")


def step_get_en_zh_bio_ids(**kwargs) -> pl.DataFrame:
    try:
        en_bio_ids = ['Donald_Trump','Jiang_Zemin', 'Zhajiangmian', 'Tibet', 'Big_Ben']
        frame = pl.DataFrame({'en_bio_id': en_bio_ids})
        progress = tqdm.tqdm(total=len(frame))
        get_zh_wikiid_progress = partial(_get_zhwiki_id, progress=progress)
        frame = frame.with_columns([
            pl.col('en_bio_id').map_elements(get_zh_wikiid_progress).alias('zh_bio_id'),
        ])
        logger.info(f"Generated frame in step_get_en_zh_bio_ids: {frame}")
        return frame
    except Exception as e:
        logger.error(f"Error in step_get_en_zh_bio_ids: {e}")
        raise

@click.command()
def scrape_en_zh_bios():
    step_dict = OrderedDict()
    step_dict['step_get_id_frame'] = SingletonStep(step_get_en_zh_bio_ids, {
        'version': '001'
    })
    step_dict['step_add_person_name_column'] = SingletonStep(step_add_person_name_column, {
        'bio_frame': 'step_get_id_frame',
        'version': '001'
    })
    step_dict['step_filter_rows_zh'] = SingletonStep(step_filter_rows_zh, {
        'bio_frame': 'step_add_person_name_column', 
        'version': '001'
    })
    step_dict['step_obtain_target_en_zh_bio_ids'] = SingletonStep(step_obtain_target_en_zh_bio_ids, {
        'bio_frame': 'step_filter_rows_zh',
        'version': '007'
    })
    step_dict['step_load_zh_bios'] = SingletonStep(step_load_zh_bios, {
        'en_zh_bio_ids_names': 'step_obtain_target_en_zh_bio_ids',
        'version': '001'
    })

    metadata = conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, "scrape_en_zh_bios")


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
        "zh": ["参见", "参考资料", "外部链接"],
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
        header_match = re.match(r'^(=+)(.*?)=+$', line)
        if header_match:
            header_text = header_match.group(2).strip().lower()
            
            # If the detected header is in the ignore list, stop processing
            if lang in ignore_headers and header_text in ignore_headers[lang]:
                break  
            
            processed_paragraphs.append({"header": header_text})
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
    topic = input("Enter Wikipedia article title (e.g., Albert Einstein): ")
    lang = input("Enter Wikipedia language code (default: en): ") or "en"
    tgt_lang = input("Enter the targeted language you would like to scrape for this topic")
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
    metadata = conduct(os.path.join(SCRATCH_DIR, "bio_scrape_cache"), step_dict, f"new_scrape_en_{tgt_lang}_bios")





@click.group()
def main():
    pass

main.add_command(scrape_french_bios_lgbtbiocorpus) # for replicating EMNLP'24
main.add_command(scrape_russian_bios_lgbtbiocorpus) # for replicating EMNLP'24
main.add_command(scrape_people_categories) # covariates for regression analysis in EMNLP'24
main.add_command(scrape_ablation_bios)
main.add_command(scrape_en_fr_bios)
main.add_command(scrape_en_zh_bios) 

main.add_command(scrape_bios)


if __name__ == '__main__':
    main()
    # bio_frame = load_artifact_with_step_name(metadata, "step_load_pairs_common")
    # bio_ids = load_bios()
    # extract_bios_en_fr(bio_ids)