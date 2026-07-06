# utils/twitter_threading.py -- Utility to split summaries into tweet threads

import re

MAX_TWEET_LENGTH = 280

# Split text by sentence boundaries
def split_sentences(text):
    return re.split(r'(?<=[.!?]) +', text.strip())

def generate_tweet_thread(summary, title="", url="", hashtags=None):
    """
    Converts a long summary into a tweet thread (list of strings), respecting the 280-character limit.
    Automatically appends a final tweet with hashtags and URL.
    """
    hashtags = hashtags or []
    sentences = split_sentences(summary)
    thread = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= MAX_TWEET_LENGTH:
            current += (" " if current else "") + sentence
        else:
            thread.append(current.strip())
            current = sentence

    if current:
        thread.append(current.strip())

    # Prepend title to the first tweet
    if title:
        if thread and len(thread[0]) + len(title) + 1 <= MAX_TWEET_LENGTH:
            thread[0] = f"{title}\n{thread[0]}"
        else:
            thread.insert(0, title)

    # Final tweet: url (+ hashtags if any)
    tag_block = " ".join(hashtags)
    closing = f"{url}\n{tag_block}".strip() if tag_block else url
    if len(closing) > MAX_TWEET_LENGTH:
        closing = url

    thread.append(closing)
    return thread
