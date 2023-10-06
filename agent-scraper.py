import os
import requests
from bs4 import BeautifulSoup

def scrape_list(url, folder_name, file_name):
    """
    Find and scrape strings from a url to build a list of user agents
    """

    # Create a folder to store the results
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Generate headers
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) ' +
               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

    # Get the page
    try:
        page = requests.get(url, headers=headers, timeout=5)
    except requests.exceptions.Timeout:
        print(f"Request timed out.")
        return
    #print(f'{url} + status code: {page.status_code} + header: {page.headers}') 
    if page.status_code == 200:
        soup = BeautifulSoup(page.content, 'html.parser')
        #print(f'html: {soup.prettify()}')
        
        # Find the table
        tables = soup.find_all('table', class_='table table-striped') # adjust class name as appropriate
        results = 0
        if tables:
            with open(folder_name + '/' + file_name, 'w') as f:
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td') # (['th, td']) to return header and data cells
                        if len(cells) > 0:
                            str = cells[0].get_text()
                            results+=1
                            f.write(str + '\n')
                print(f'Wrote {results} items to {folder_name}/{file_name}')
        else:
            print('No table found')
    else:
        print(f'Error accessing {url}: Status Code: {page.status_code}')

# takes url target, desired output folder directory and file name as params
scrape_list('URL_Here', 'Folder_Here', 'Output_File.txt')  