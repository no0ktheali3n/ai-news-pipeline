# summarizer_lambda.py – Lambda handler for AWS deployment

from summarizer import summarize_articles

def lambda_handler(event, context):
    summaries = summarize_articles()
    return {
        "statusCode": 200,
        "body": summaries
    }
