# Contact
Email: `fsamir@mail.ubc.ca`, `zining.wang@ubc.ca`

<!-- # Artifacts
Our analysis dataframes from Section 3 of our paper are here, in JSON format (about ~600MB each):
1. [En<->Fr](https://www.dropbox.com/scl/fi/oxdphmcxaai2ur7swoz1l/connotation_df_en_fr_flan.json?rlkey=pz82ygv8rx2xybkvv1eaavbo3&st=or1r65no&dl=0)
2. [En<->Ru](https://www.dropbox.com/scl/fi/kavcip55wvbfegaafxy5b/connotation_df_en_ru_mt5.json?rlkey=q7wpn8n6ahwp6xg6vd3g9ogub&st=qw5vvi2z&dl=0) -->

You can process them with the `polars` package (`pl.read_json(...)`). `pandas` should also work. I recommend inspecting these dataframes before trying out the pipeline on your own documents.  

# Running the pipeline yourself for generating Json output files for WikiGap extension
<!-- ## I. Install flowmason
1. Clone the repo: `git clone https://github.com/smfsamir/flowmason`
2. Go into directory: `cd flowmason`
3. Checkout the `abstract` branch: `git checkout abstract`
4. Install the package locally `pip install -e .` -->

<!-- ## II. Install wikipedia-edit-scrape-tool
1. Clone the repo: `git clone https://github.com/smfsamir/wikipedia-edit-scrape-tool`
2. Go into directory: `cd wikipedia-edit-scrape-tool`
3. Install the package locally `pip install -e .` -->

## I. Set up an Environment file
The purpose of the `.env` is to set configuration environment variables specific to you. Don't commit this. 
1. In `infogap` project directory, run `touch .env`
2. Create two keys: `SCRATCH_DIR` (where all the artifacts from the pipeline will be stored), and `THE_KEY`, an OpenAI key.


## II. Install requirements
`pip install -r requirements.txt` (It's possible I missed a couple of modules here, please submit a PR if you find that to be the case and I'll approve right away). 

## III. Scrape the articles you want.   
To scrape text from Wikipedia for a list of topics:
1. Specify the Topics
Open the file `wikigap_topics_scrape.py` and modify the list to include the Wikipedia article titles you want to scrape.
• Each topic should match the exact title used on Wikipedia. You can refer to the examples already included for our CSCW 2026 paper.
2. Run the Scraper
From the project root directory, run the following command in your terminal: `python main_scrape_bios.py scrape-bios`

3. Choose Target Language
After running the command, you will be prompted to enter the target language code (e.g., fr for French, zh for Chinese).
• These codes should follow the ISO 639-1 language codes.
• The scraper will fetch articles in the target language for each topic listed in wikigap_topics_scrape.py, using the English titles as a reference.
4. Output Location
The scraped results will be saved to the path specified by your SCRATCH_DIR variable in your .env file.

## IV. Run the InfoGap Pipeline

To run the InfoGap analysis between English and a target language, use the following command:

`python main_complete_analysis.py run-multiple-topics`

This script reads pairs of scraped article titles from language-specific files named:

`scraped_titles_{lang}.py`

These files are located in the packages/ folder.

When prompted with:

Enter the target language code you would like to analyze for the scraped topics (zh, ru, fr):

the script retrieves the corresponding article pairs and iteratively analyzes them.

### Pipeline Overview

The core pipeline logic is defined in packages/steps/map_dicts.py in the function get_en_tgt_info_diff_map_dict. This function builds a sequence of SingletonSteps to:
	•	Retrieve pre-scraped content blocks
	•	Generate facts from each article
	•	Align and union fact-paragraph associations
	•	Identify cross-lingual fact matches
	•	Apply GPT-based reasoning to detect information gaps

### Example Steps

Retrieve Target-Language Content Blocks

```python
map_reduce_dict['step_get_tgt_content_blocks'] = SingletonStep(
    step_retrieve_prescraped_tgt_content_blocks,
    {
        'version': '003',
        **tgt_bio_id_dict,
        **tgt_lang_dict
    }
)
```

Generate Facts with LLM for Target Language

```python
map_reduce_dict['step_generate_facts_tgt'] = SingletonStep(
    step_generate_facts,
    {
        'version': '002',
        'lang_code': tgt_lang,
        'content_blocks': 'step_get_tgt_content_blocks',
        **person_name_dict
    }
)
```

Collapse GPT Labels

```python
map_reduce_dict['step_collapse_gpt_labels'] = SingletonStep(
    step_collapse_gpt_labels,
    {
        'version': '002',
        'model_intersection_names': ('gpt-4o',),
        'gpt_info_gap_dfs': 'step_reasoning_intersection_label'
    }
)
```

This final step produces a binary label for each fact indicating whether it exists in both language editions (yes) or only in one (no).

### Pipeline Execution

The entire pipeline is executed via the function run_complete_gpt_pipeline, which internally calls the map-reduce steps and runs:

```python
        metadata = conduct(
            os.path.join(SCRATCH_DIR, f"full_cache_gpt_en_{tgt_lang}"),
            full_map_dict,
            f"en_{tgt_lang}_gpt_logs"
        )
```

This uses the flowmason framework to coordinate step execution.

You can then load the resulting artifacts with:

```python
info_gap_dfs = load_mr_artifact(metadata[0])
```

This returns a tuple of three polars DataFrames:
* info_gap_dfs[0]: DataFrame of English → Target Language direction
* info_gap_dfs[1]: DataFrame of Target Language → English direction
* info_gap_dfs[2]: Legacy placeholder (can be ignored)

Each DataFrame includes a gpt-4_intersection_label column where:
* yes = fact is found in both language editions
* no = fact is found only in the source language

### Output Location

The results are cached under:
`${SCRATCH_DIR}/full_cache`
via the flowmason package, enabling reproducibility and debugging.

## VII. Evaluating InfoGap on your documents
If you're using this for the first time, you should definitely check that the InfoGap labels are reasonably aligned with your expectations. This is what the final two steps are for:

### Preparing the annotation frame
```
full_map_dict['step_prep_annotation_frame'] = SingletonStep(step_prep_annotation_frame, { # samples 10 facts from the InfoGap frame for each direction (20 in total)
    'info_gap_dfs': 'map_step_compute_info_gap', 
    'tgt_lang_code': 'fr', 
    'intersection_label': 'gpt-4_intersection_label',
    'version': '003'
})
full_map_dict['step_add_annotation_translations'] = SingletonStep(step_add_translations_to_annotation_frame, { # adds translations for {tgt_lang_code} using NLLB-200, in case you don't read {tgt_lang_code}
    'annotation_frame': 'step_prep_annotation_frame', 
    'target_fname': 'attal_annotation_frame.json',
    'version': '001'
})
```
### Performing annotations
This will result in a JSON file that will store annotations; in this case, it is `attal_annotation_frame.json`, since we're using Gabriel Attals `En` and `Fr` pages as the running example. Then, running `python main_perform_annotation.py` should result in the following output in your terminal: 

```
2025-01-27 15:29:30.559 | INFO     | packages.annotate:annotate_frame:72 - Number of samples that are unannotated: 20
  0%|                                                                                            | 0/10 [00:00<?, ?it/s]

Consider the following fact(s) about Gabriel Attal:

1. The French media speculated that Attal was a potential contender in the 2027 presidential election.
2. On 16 January 2024, Attal made an announcement.
3. Attal announced that he would not be seeking a vote of confidence in the National Assembly.


Is the final fact present in the French Wikipedia article about Gabriel Attal (fr.wikipedia.org/wiki/Gabriel_Attal)?

Here are some snippets from the French article:
1. Emmanuel Macron a annoncé la dissolution de l'Assemblée le soir des élections européennes. (Emmanuel Macron announced the dissolution of the Assembly on the eve of the European elections.)
2. Gabriel Attal n'a pas été consulté avant l'annonce de la dissolution de l'Assemblée. (Gabriel Attal was not consulted before the dissolution of the Assembly was announced.)

1. Le 8 juillet 2024, Gabriel Attal remet sa démission et celle de son gouvernement au président de la République. (On 8 July 2024, Gabriel Attal submitted his resignation and that of his government to the President of the Republic.)
2. Le président de la République refuse la démission de Gabriel Attal. (The President of the Republic refuses the resignation of Gabriel Attal.)


A: covered by the snippets
B: partly covered by the snippets
C: covered by the article
D: partly covered by the article
E: Not in the article
Answer (A/B/C/D/E):
```
How it works:
- You read the source facts at the beginning. We provide up to two facts of previous context, but the fact of interest is the final one. In particular, whether that fact exists in the other language version.
- Suppose it does exist in the other article:
    - In this case, you will pick either A, B, C, D
    - You pick A or B when the target fact is shown in the small set of snippets from the other language version
    - Otherwise you pick C or D. To select C or D, you'll have to go through the other language version's article directly on Wikipedia and see if you can find the fact in there.
- Otherwise, you pick E. 


A few things to note:
- You can see at the start of the annotation, the total number of samples in the annotation JSON that haven't been annotated (at the beginning this will be 20).
- A progress bar that says 0/10. This may be confusing because there are 20 samples to be annotated. This is because I try to annotate 10 samples per sitting (each annotation is not easy since you may have to read the target article in full to see whether the fact is listed/inferrable or not. You can annotate more than 10 in one sitting by changing the `num_samples` parameter in the call to `annotate_frame` in `main_perform_annotation.py`.
- When you finish all 10 (for the sitting), or Ctrl+C and exit, your annotations will be saved. Next time you run the annotation, the terminal output will show that you have `20-n` annotations to complete.
- It's also instructive to read Section 2.3 of the [paper](https://arxiv.org/pdf/2410.04282) to understand the terminal content for each datapoint. 



# Citation
```
@inproceedings{samir-2024-information,
    title = "Locating Information Gaps and Narrative Inconsistencies Across Languages: A Case Study of LGBT People Portrayals on Wikipedia",
    author = "Samir, Farhan  and
      Park, Chan Young and
      Field, Anjalie and
      Shwartz, Vered and 
      Tsvetkov, Yulia",
    editor = "Al-Onaizan, Yaser and
      Bansal, Mohit and
      Chen, Yun-Nung",
    booktitle = "Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing",
    month = nov,
    year = "2024",
    address = "Miami",
    publisher = "Association for Computational Linguistics"
}
```
