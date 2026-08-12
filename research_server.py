import arxiv
import json
import os
import re
from dotenv import load_dotenv
from openai import OpenAI
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("research", port=int(os.environ.get("PORT", 8001)), host="0.0.0.0")


PAPER_DIR = os.path.join(os.getcwd(), "papers")

@mcp.tool()
def search_papers(topic: str, max_results: int = 5):
    """Search arxiv for a topic and store the results' info to disk.

    Args:
        topic: the topic to search for
        max_results: the maximum number of results to retrieve

    Returns:
        list of paper IDs found in the search
    """
    client = arxiv.Client()
    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    results = list(client.results(search))

    # Sanitize topic so it's safe to use as a directory name
    safe_topic = re.sub(r"[^a-z0-9_-]+", "_", topic.lower()).strip("_")
    file_path = os.path.join(PAPER_DIR, safe_topic)
    id_file_path = os.path.join(file_path, "papers_info.json")

    os.makedirs(file_path, exist_ok=True)

    try:
        with open(id_file_path, "r") as file:
            papers_info = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    papers_id = []
    for paper in results:
        short_id = paper.get_short_id()
        papers_id.append(short_id)
        papers_info[short_id] = {
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": paper.summary,
            "pdf_url": paper.pdf_url,
            "published": str(paper.published.date()),
        }

    # Write once, after the loop, not on every iteration
    with open(id_file_path, "w") as file:
        json.dump(papers_info, file, indent=2)
    print(f"Results saved in {id_file_path}")

    return papers_id

@mcp.tool()
def extract_info(paper_id: str):
    """Search for information about a specific paper across all topic directories.

    Args:
        paper_id: the id of the paper to look for

    Returns:
        JSON string with paper information if found, error message if not found
    """
    if not os.path.isdir(PAPER_DIR):
        return f"There is no saved information related to paper with ID {paper_id}."

    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, "papers_info.json")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r") as file:
                        papers_info = json.load(file)
                        if paper_id in papers_info:
                            return json.dumps(papers_info[paper_id], indent=2)
                except (FileNotFoundError, json.JSONDecodeError):
                    continue

    return f"There is no saved information related to paper with ID {paper_id}."



@mcp.resource("papers://folders")
def get_available_foolders()->str:
    """
    list all available topic folders in the papers directory.
    this resource provides a list of all available topic folders.
    """

    folders = []
    if os.path.exists(PAPER_DIR):
        for topic_dir in os.listdir(PAPER_DIR):
            topic_path = os.path.join(PAPER_DIR,topic_dir)
            if os.path.isdir(topic_path):
                papers_file = os.path.join(topic_path, "papers_info.json")
                if os.path.exists(papers_file):
                    folders.append(topic_dir)

    #create a markdown list
    content = "# Available Topics\n\n"
    if folders:
        for folder in folders:
            content+=f"- {folder}\n"
        content += f"\n Use @{folder} to access papers in that topic"
    else:
        content+="No topic found\n"

    return content

@mcp.resource("papers://{topic}")
def get_topic_papers(topic:str)->str:
    """
    Get detailed information about papers on a specific topic

    Args:
        topic: the research topic to retrieve papers for
    """

    topic_dir = topic.lower().replace(" ","_")
    papers_file = os.path.join(PAPER_DIR, topic_dir, "papers_info.json")

    if not os.path.exists(papers_file):
        return f"#No found for topic: {topic}\n\n Try searching for papers in this topic first"

    try:
        with open(papers_file,'r') as file:
            papers_data = json.load(file)

        content = f"# papers on topic {topic.replace('_',' ').title()}\n\n "
        content+=f"total papers: {len(papers_data)}\n\n"

        for paper_id, paper_info in papers_data.items():
            content += f"## {paper_info['title']}" #create this dictionary
            content+= f"- **Paper ID**: {paper_id}\n"
            content+=f"- **Authors**: {','.join(paper_info['authors'])}\n"
            content+=f"- **Published**: {paper_info['published']}"
            content+=f"- **PDF URL**: {paper_info['pdf_url']}\n"
            content+=f"### Summary\n{paper_info['summary'][:500]}...\n\n"
            content+="---\n\n"
        return content
    except json.JSONDecodeError:
        return f"# Error reading papers data for {topic}\n\nThe papers data file is corrupted "

@mcp.prompt()
def generate_search_prompt(topic:str, num_papers: int=5)->str:
    """Generate a prompt for claude to find and discuss academic papers on a specific topic"""
    return f"""search for {num_papers} academic papers about '{topic}' using the search_papers tool. Follow these instructions:
    1. First, search for papers using search_papers(topic='{topic}',max_results={num_papers})
    2. for each paper found,extract and organize the following information:
        -Paper title
        -Authors
        -Publication date
        -Brief summary of the key findings
        -Main contributions or innovations
        -Methodologies used
        -Relevance to the topic '{topic}'

    3. provide a comprehensive summary that includes:
        - Overview of the current state of research in '{topic}'
        - Common themes and trends across the papers
        - Key research gaps or areas for future investigation
        - Most impactful or influential papers in this area

    4. Organize your findings in a clear, structured format with headings and bullet points for easy readability.

    please present both detailed information about each paper and a high level synthesis of the research landscape in {topic}.
    """


    




        







if __name__ == "__main__":
    mcp.run(transport='streamable-http')