# InfoGap: A Tool for Analyzing Cross-Lingual Information Disparities in Wikipedia


### Contact

Email: `fsamir@mail.ubc.ca`, `zining.wang@ubc.ca`

### Running the Pipeline

To run the InfoGap pipeline, follow these steps:

1. **Set up an Environment file**:
	* Create a `.env` file in the project root directory.
	* Add two environment variables: `SCRATCH_DIR` and `THE_KEY`.
	* `SCRATCH_DIR` should point to a directory where the pipeline will store its artifacts.
	* `THE_KEY` should contain your OpenAI API key.
2. **Install requirements**:
	* Run `pip install -r requirements.txt`.
3. **Scrape the articles you want**:
	* Modify the `wikigap_topics_scrape.py` file to include the topics you want to scrape.
	* Run `python main_scrape_bios.py scrape-bios`.
	* The script will prompt you to enter the target language code.
	* The scraped results will be saved to the path specified by `SCRATCH_DIR`.
4. **Run the InfoGap pipeline**:
	* Run `python main_complete_analysis.py run-multiple-topics`.
	* The script will read pairs of scraped article titles from language-specific files named `scraped_titles_{lang}.py`.
	* The script will then analyze the scraped articles and generate the output.

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

This uses the flowmason framework to coordinate step execution. You can then load the resulting artifacts with:

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
* Step 3 of function `run_complete_gpt_pipeline` will save both info_gap_dfs[0] and info_gap_dfs[1] to the `ethnic_annotation_save/wikigap_data` directory. Those are saved as a json file named `{topic}.json`. These json files are considered as annotations, and will be the input to the process annotation step.

> Note: For debugging purposes, each single step's output are cached under:`${SCRATCH_DIR}/full_cache`via the flowmason package.

## VII. Process annotations and Format InfoGap Output for WikiGap
> Since the WikiGap research relies on automatic knowledge alignment using LLMs, we didn't incorporate the mannual annotation step in the pipeline to generate the WikiGap datasets. This is different from the original InfoGap research where the accuracy and reliability of the automatic alignment was evaluated using manual annotations.

After running the InfoGap pipeline, the next step is to transform the output into a structured, translated, and filtered dataset ready for integration with the WikiGap Chrome extension. This is done using the script:

```bash
python process_annotations.py
```

This script converts raw JSON outputs from the InfoGap pipeline into paragraph-aligned, cross-lingual knowledge discrepancy datasets, organized per article and per language, and saved as nested JSON for WikiGap extension use.

### What process_annotations.py Does
1. Loads and parses the InfoGap .json output files (one per article and language).
2. Retrieves and processes corresponding paragraph blocks for English and target-language articles.
3. Matches each fact to its paragraph and associated section headers (e.g., header_1, header_2).
4. Filters for language-specific facts (i.e., intersection_label == 'no').
5. Translates headers and facts to English using:
    * Google Translate (headers)
    * GPT-4o via Azure OpenAI (facts)
6. Samples facts per header section (optional).
7. Generates a nested JSON structure organized by person → language → section → facts, ready to be loaded by the WikiGap extension.

### Input/Output File Structure

Input JSONs:
From the pipeline, located in:

scratch/ethics_annotation_save/wikigap_data/annotation_{date}_{en_title}_{lang}.json


Paragraph Blocks (pickled):
From preprocessing step:

scratch/wiki_food/{bio_id}_{lang}.pkl


Output JSONs:
Saved per topic to:

scratch/ethics_annotation_save/wikigap_data/json/{topic}.json


How to Run the Script

Make sure the following are set up:
1. The packages.scraped_titles_{lang}.py files exist and contain en_tgt_title_pairs
2. The wikigap_topics_scrape.py file has a selected_topics list
3. Environment variables for Azure OpenAI:

```bash
export THE_KEY=your-azure-api-key
export URL_ENDPOINT=https://your-azure-endpoint.openai.azure.com/
```

Then run:

```bash
python process_annotations.py
```


### How to Interpret the Output

Each final .json file is organized like:
```json
{
  "topic_name": {
    "languages": {
      "fr": {
        "headers": {
          "Cultural Background": {
            "entries": [
              {
                "fact": {
                  "original": "Le plat est souvent servi lors des mariages.",
                  "translated": "The dish is often served at weddings.",
                  ...
                },
                "header_1": {
                  "original": "Cultural Background",
                  "translated": "Cultural Background"
                },
                ...
              }
            ]
          }
        }
      }
    }
  }
}
```

Only facts labeled with intersection_label == 'no' are included (i.e., knowledge present in one language but missing in the other).

### Optional: Enable Sampling

To sample a subset of facts per header (e.g., 15 per section), enable this line in main():

```python
df_tgt_sampled = weighted_sampling_by_header(df_filtered, header_column="header_1", sample_size=15)
```



### Citation
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
