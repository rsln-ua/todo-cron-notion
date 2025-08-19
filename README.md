# Notion To-Do Automation

This project automates daily resets and logging for your Notion to-do list.

## Features
- Unchecks all tasks in **Daily** every night and logs them in **Daily Completion**.
- Moves unfinished tasks from **Today** to **Backlog**.
- Moves **Tomorrow** tasks into **Today** automatically.
- Deletes completed tasks from **Today** and **Backlog**, saving them into **Done**.

## Setup

1. **Duplicate the template**  
   Use the Notion template here: [Notion To-Do Template](https://ruslank.notion.site/To-Do-List-254df39e1845805abc25d97f90b81a67)

2. **Create an integration**  
   - Go to [Notion Integrations](https://www.notion.so/my-integrations).  
   - Create a new integration and copy the **Internal Integration Token**.

3. **Share the page with the integration**  
   - In Notion, open your duplicated template.  
   - Click **Share** → add your integration with **Can edit** permission.

4. **Get your NOTION_PAGE_ID**  
   - Open the page in a browser.  
   - Copy the long ID from the URL (after the last `/`).  

## Environment variables

Set the following environment variables:

```bash
NOTION_TOKEN=your_secret_token
NOTION_PAGE_ID=your_page_id
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export NOTION_TOKEN=...
export NOTION_PAGE_ID=...
python main.py
```

## Run with GitHub Actions

A ready-to-use GitHub Actions workflow is included at `.github/workflows/daily-update.yml`. It runs the script daily.
