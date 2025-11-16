import re
import tqdm
import json
import openai
import logging
import argparse

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

URL_ENDPOINT = os.getenv("URL_ENDPOINT")
INSTRUCTIONS = "Generate a single sentence to continue this narrative."  # Change to your task

def main():
    parser = argparse.ArgumentParser()

    # Required parameters
    parser.add_argument(
        "--openai_api_key",
        default=None,
        type=str,
        required=True,
        help="API key to use Azure.",
    )
    parser.add_argument(
        "--eval_file",
        default=None,
        type=str,
        required=True,
        help="The dev/test set json file from which examples will be used for evaluation.",
    )
    parser.add_argument(
        "--out_prediction_file",
        default=None,
        type=str,
        required=True,
        help="Where to save the predictions.",
    )

    # Optional parameters
    parser.add_argument(
        "--model",
        default="gpt-35-turbo",
        type=str,
        required=False,
        help="Which OpenAI model to use (gpt-35-turbo or gpt4).",
    )
    args = parser.parse_args()

    client = openai.AzureOpenAI(
        api_key=args.openai_api_key,
        api_version="2023-05-15",
        azure_endpoint=URL_ENDPOINT)

    # Get the test examples
    test_examples = [json.loads(ex) for ex in open(args.eval_file)]

    predictions, filtered = solve(client, args.model, test_examples, args.out_prediction_file)
    logger.debug(f"Number of filtered examples: {filtered}")

def create_prompt(ex):
    narrative = ex["narrative"].replace('<b>', '').replace('</b>', '')  # change according to your task 
    return narrative

def solve(client, model, test_examples, prediction_file):
    """
    Test the model with few-shot learning
    :param client: the OpenAI client
    :param test_examples: list of dicts {"narrative", "plausible"}
    :return: the predictions
    """
    prompt = INSTRUCTIONS + "\n"
    logger.debug(prompt)
    filtered = 0

    # Save the predictions
    with open(prediction_file, "w") as f_out:
        predictions = []
        for ex in tqdm.tqdm(test_examples):
            try:
                pred = client.chat.completions.create(
                    model=model,
                    max_tokens=40,
                    messages=[
                        {"role": "system", "content": "Assistant is a large language model trained by OpenAI."},
                        {"role": "user", "content": f"{prompt}{create_prompt(ex)}"}
                    ]).choices[0].message.content
            except:
                pred = ""
                filtered += 1
            finally:
                ex = {"input": ex["narrative"], "gold": ex["correctanswer"], "prediction": pred}  # change according to your task 
                predictions.append(pred)
                f_out.write(json.dumps(ex) + "\n")
                f_out.flush()

    return predictions, filtered

if __name__ == "__main__":
    main()
