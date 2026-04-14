import requests
import pandas as pd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import time

# ---------------- 配置区 ----------------
# 时间窗口：抓取过去 24 小时的数据
TODAY = datetime.utcnow()
YESTERDAY = TODAY - timedelta(days=1)

# 基础检索词 (以你的“总预览”为基础，由于 API 限制，MVP 阶段我们用核心词汇保证连通性)
CORE_QUERY = '("virtual cell" OR "digital cell" OR "whole-cell model" OR "cell digital twin")'

def fetch_pubmed():
    """通过 PubMed E-utilities API 获取数据"""
    print("⏳ 正在请求 PubMed...")
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    # 1. Search 获取 ID (限定近1天)
    term = f'{CORE_QUERY} AND ("{YESTERDAY.strftime("%Y/%m/%d")}"[Date - Publication] : "{TODAY.strftime("%Y/%m/%d")}"[Date - Publication])'
    search_res = requests.get(f"{base_url}esearch.fcgi", params={
        "db": "pubmed", "term": term, "retmode": "json", "retmax": 50
    }).json()
    
    id_list = search_res.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    # 2. Summary 获取详情
    summary_res = requests.get(f"{base_url}esummary.fcgi", params={
        "db": "pubmed", "id": ",".join(id_list), "retmode": "json"
    }).json()
    
    papers = []
    for uid in id_list:
        doc = summary_res.get("result", {}).get(uid, {})
        authors = [auth.get("name", "") for auth in doc.get("authors", [])]
        doi = next((idx.get("value") for idx in doc.get("articleids", []) if idx.get("idtype") == "doi"), "N/A")
        
        papers.append({
            "来源数据库": "PubMed",
            "发表日期": doc.get("pubdate", ""),
            "文章标题": doc.get("title", ""),
            "作者列表": ", ".join(authors),
            "DOI 链接": f"https://doi.org/{doi}" if doi != "N/A" else ""
        })
    return papers

def fetch_arxiv():
    """通过 arXiv API 获取 CS 和 Q-Bio 分类下的预印本"""
    print("⏳ 正在请求 arXiv...")
    # arXiv 的日期过滤较为特殊，这里我们在查询中直接做简单的日期范围限制
    query = f'all:"virtual cell" OR all:"digital cell"'
    url = f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=20"
    
    response = requests.get(url)
    root = ET.fromstring(response.text)
    ns = {'arxiv': 'http://www.w3.org/2005/Atom'}
    
    papers = []
    for entry in root.findall('arxiv:entry', ns):
        pub_date = entry.find('arxiv:published', ns).text[:10]
        # MVP 阶段简单过滤近 2 天的数据
        if pub_date >= YESTERDAY.strftime("%Y-%m-%d"):
            authors = [author.find('arxiv:name', ns).text for author in entry.findall('arxiv:author', ns)]
            doi_link = entry.find('arxiv:id', ns).text
            title = entry.find('arxiv:title', ns).text.replace('\n', ' ').strip()
            
            papers.append({
                "来源数据库": "arXiv",
                "发表日期": pub_date,
                "文章标题": title,
                "作者列表": ", ".join(authors),
                "DOI 链接": doi_link
            })
    return papers

def fetch_crossref_top_journals():
    """通过 Crossref 获取 Nature, Science, Cell 的最新文章"""
    print("⏳ 正在请求 Crossref (顶刊监控)...")
    # 顶刊 ISSN: Nature (0028-0836), Science (0036-8075), Cell (0092-8674)
    issns = "0028-0836,0036-8075,0092-8674"
    url = "https://api.crossref.org/works"
    params = {
        "query": CORE_QUERY,
        "filter": f"issn:{issns},from-pub-date:{YESTERDAY.strftime('%Y-%m-%d')}",
        "select": "title,author,issued,DOI,container-title",
        "rows": 20
    }
    
    try:
        res = requests.get(url, params=params).json()
        items = res.get("message", {}).get("items", [])
    except Exception:
        return []

    papers = []
    for item in items:
        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])]
        date_parts = item.get("issued", {}).get("date-parts", [[None]])[0]
        pub_date = "-".join(map(str, date_parts)) if date_parts[0] else ""
        journal = item.get("container-title", [""])[0]
        
        papers.append({
            "来源数据库": f"Crossref ({journal})",
            "发表日期": pub_date,
            "文章标题": item.get("title", [""])[0],
            "作者列表": ", ".join(authors),
            "DOI 链接": f"https://doi.org/{item.get('DOI', '')}"
        })
    return papers

if __name__ == "__main__":
    print(f"🚀 开始抓取 {YESTERDAY.strftime('%Y-%m-%d')} 至 {TODAY.strftime('%Y-%m-%d')} 的文献...")
    
    all_data = []
    all_data.extend(fetch_pubmed())
    time.sleep(1) # 礼貌性延时
    all_data.extend(fetch_arxiv())
    time.sleep(1)
    all_data.extend(fetch_crossref_top_journals())
    
    if all_data:
        df = pd.DataFrame(all_data)
        filename = f"VirtualCell_DailyReport_{TODAY.strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig') # utf-8-sig 防止 Excel 乱码
        print(f"✅ 抓取完成！共发现 {len(df)} 篇新文献。已保存至: {filename}")
    else:
        print("📭 今日未检索到符合条件的新文献。")