import loguru 
from typing import List, Union
from wikipedia_edit_scrape_tool import get_text, Header, Paragraph 

logger = loguru.logger

def remove_person_specific_blocks_fr(fr_bio_id, content_blocks):
    if fr_bio_id == 'Abdellah_Taïa':
        # filter out paragraph after "Sur quelques ouvrages > La vie lente"
        sur_quelques_ouvrages_header_index = [i for i, block in enumerate(content_blocks) if isinstance(block, Header) and block.text == "Sur quelques ouvrages"][0] 
        return content_blocks[:sur_quelques_ouvrages_header_index]
    elif fr_bio_id == 'Frédéric_Mitterrand':
        s = 'prix et récompenses suivants'
        # filter out paragraph including and after "prix et récompenses suivants"
        prix_et_recompenses_index = [i for i, block in enumerate(content_blocks) if isinstance(block, Paragraph) and s in block.clean_text][0]
        return content_blocks[:prix_et_recompenses_index]
    else:
        return content_blocks

def step_retrieve_en_content_blocks(en_bio_id: str, 
                                 **kwargs) -> List[Union[Header, Paragraph]]:
    """Return all of the headers and paragraphs from the English Wikipedia page 
    for the person with the given bio id.
    """
    english_id = en_bio_id
    en_link = f"https://en.wikipedia.org/wiki/{english_id}"
    content_blocks = get_text(en_link, 'enwiki')
    # filter out paragraphs where the clean_text attribute string has fewer than 6 words.
    content_blocks = list(filter(lambda x: not (isinstance(x, Paragraph) and len(x.clean_text.split()) < 6), content_blocks))
    return content_blocks 

def step_retrieve_fr_content_blocks(fr_bio_id: str, 
                                 **kwargs) -> List[Union[Header, Paragraph]]:
    french_id = fr_bio_id
    fr_link = f"https://fr.wikipedia.org/wiki/{french_id}"
    content_blocks = get_text(fr_link, 'frwiki')
    num_blocks_orig = len(content_blocks)
    # voir_aussi_header = next(filter(lambda x: isinstance(x, Header) and x.text == "Voir aussi" , content_blocks))
    # check if content blocks has voir aussi header
    if any([isinstance(block, Header) and block.text == "Voir aussi" for block in content_blocks]):
        voir_aussi_header = next(filter(lambda x: isinstance(x, Header) and x.text == "Voir aussi" , content_blocks))
        voir_aussi_index = content_blocks.index(voir_aussi_header)
        content_blocks = content_blocks[:voir_aussi_index]
        # log that we're omitting the "Voir aussi" section and everything after it
        logger.info(f"Omitting the 'Voir aussi' section and everything after it for the French Wikipedia page for {fr_bio_id}. This drops {num_blocks_orig - len(content_blocks)} blocks")
    content_blocks = remove_person_specific_blocks_fr(fr_bio_id, content_blocks)
    content_blocks = list(filter(lambda x: not (isinstance(x, Paragraph) and len(x.clean_text.split()) < 6), content_blocks)) # filter out paragraphs where the clean_text attribute string has fewer than 6 words.
    return content_blocks

def step_retrieve_ru_content_blocks(ru_bio_id: str, 
                                    **kwargs): 
    ru_bio_id = ru_bio_id
    ru_link = f"https://ru.wikipedia.org/wiki/{ru_bio_id}"
    content_blocks = get_text(ru_link, 'ruwiki')
    return content_blocks