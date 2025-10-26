from fastapi import FastAPI, Query
import httpx
from xml.etree import ElementTree as ET

app = FastAPI(
    title="Dent-R PubMed API",
    description="Returns PubMed search results as clean JSON. No hallucinations.",
    version="1.0.0"
)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def extract_article_info(xml_text: str):
    root = ET.fromstring(xml_text)

    # タイトル
    title = root.findtext(".//ArticleTitle")

    # アブストラクト（抄録）
    abstract_parts = [t.text for t in root.findall(".//AbstractText") if t.text]
    abstract_full = " ".join(abstract_parts)

    # 著者
    authors_list = []
    for author in root.findall(".//Author"):
        last = author.findtext("LastName")
        fore = author.findtext("ForeName")
        if last and fore:
            authors_list.append(f"{fore} {last}")
    authors = ", ".join(authors_list)

    # 雑誌名
    journal = root.findtext(".//Journal/Title")

    # 出版年（年がとれないケースの保険も入れる）
    year = root.findtext(".//PubDate/Year")
    if year is None:
        year = root.findtext(".//ArticleDate/Year")

    return {
        "title": title if title else "",
        "authors": authors if authors else "",
        "journal": journal if journal else "",
        "year": year if year else "",
        "abstract": abstract_full if abstract_full else ""
    }

@app.get("/pubmed_search")
async def pubmed_search(term: str = Query(..., description="PubMed search term"),
                        retmax: int = Query(10, description="Max number of articles")):
    """
    term   : PubMedで検索したい語句（例: 'zirconia AND bonding strength'）
    retmax : 何件ほしいか
    """

    # 1. PMID一覧を取得
    async with httpx.AsyncClient() as client:
        esearch_res = await client.get(
            f"{NCBI_BASE}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": term,
                "retmax": retmax,
                "retmode": "xml"
            }
        )
    # PMIDをXMLから抜く
    esearch_root = ET.fromstring(esearch_res.text)
    pmid_list = [n.text for n in esearch_root.findall(".//Id")]

    results = []

    # 2. 各PMIDごとに詳細を取得
    for pmid in pmid_list:
        async with httpx.AsyncClient() as client:
            efetch_res = await client.get(
                f"{NCBI_BASE}/efetch.fcgi",
                params={
                    "db": "pubmed",
                    "id": pmid,
                    "retmode": "xml"
                }
            )

        article_info = extract_article_info(efetch_res.text)

        # 文字数制限：抄録をそのまま全部配るのが出版社的にイヤならここで短縮する
        MAX_ABSTRACT_CHARS = 1200  # 必要に応じて調整
        if len(article_info["abstract"]) > MAX_ABSTRACT_CHARS:
            article_info["abstract"] = article_info["abstract"][:MAX_ABSTRACT_CHARS] + " ...[truncated]"

        # PMIDも入れる
        article_info["pmid"] = pmid

        results.append(article_info)

    return {
        "query": term,
        "count": len(results),
        "results": results
    }
