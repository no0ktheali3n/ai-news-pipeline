import requests

#constants
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/tyy2u5jewfu7y215nudb6fcxaf5awu0y" 

def notify_make_pipeline_status(articles=None, message=None):
    """
    Sends a notification to a Make webhook with the provided articles and/or message.
    Args:
        articles (list, optional): A list of articles to include in the notification. Defaults to None.
        message (str, optional): A message to include in the notification. Defaults to None.
    Raises:
        requests.exceptions.RequestException: If the HTTP request to the Make webhook fails.
    Notes:
        - The function sends a POST request to the Make webhook URL defined by the `MAKE_WEBHOOK_URL` variable.
        - The payload includes the `message` and/or `articles` if provided.
        - Logs a success message if the webhook is sent successfully, otherwise logs the error.
    """
    data = {}    
    if message:
        data["message"] = message
    if articles is not None:
        data["articles"] = articles

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(MAKE_WEBHOOK_URL, json=data, headers=headers)
        response.raise_for_status()
        print("Make webhook sent.")
    except requests.exceptions.RequestException as e:
        print(f"Make webhook error: {e}")