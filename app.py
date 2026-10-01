import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def crawl_incruit(keyword):
    """인크루트 검색 결과에서 공고 제목/기업명/링크를 추출합니다."""
    jobs = []
    url = "https://search.incruit.com/list/search.asp"
    params = {"col": "all", "src": "gsw", "kw": keyword}

    response = requests.get(
        url, params=params, headers=HEADERS, timeout=20
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # 사용자가 제공한 화면에서 확인한 공고 카드 구조를 우선 사용합니다.
    cards = soup.select(".cbs_list_content ul.c_row")
    if not cards:
        cards = soup.select("ul.c_row")

    seen = set()
    for card in cards:
        # 상세 공고 링크가 들어 있는 a 태그를 찾습니다.
        anchors = card.select('a[href*="jobpost.asp"]')
        for anchor in anchors:
            href = anchor.get("href", "").strip()
            link = urljoin(response.url, href)
            title = clean_text(anchor.get_text(" ", strip=True))

            # 일부 링크는 제목 텍스트가 비어 있어 카드의 텍스트로 보완합니다.
            if not title:
                title = clean_text(card.get_text(" ", strip=True))

            if not href or not title or link in seen:
                continue

            company_tag = card.select_one("a.cpname")
            if company_tag:
                company = clean_text(company_tag.get_text(" ", strip=True))
            else:
                company = "기업명 확인 필요"

            # 버튼/스크랩 등의 링크가 공고 링크로 잡히는 경우를 줄이기 위해
            # 제목 텍스트가 있는 링크를 우선 수집합니다.
            jobs.append({
                "site": "인크루트",
                "title": title,
                "company": company,
                "link": link,
            })
            seen.add(link)

    return jobs


def crawl_jobkorea(keyword):
    """잡코리아 검색 결과에서 공고 링크를 찾아 정보를 추출합니다."""
    jobs = []
    url = "https://www.jobkorea.co.kr/Search/"
    params = {"stext": keyword}

    response = requests.get(
        url, params=params, headers=HEADERS, timeout=20
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # 잡코리아 공고 URL 패턴을 기준으로 링크를 찾습니다.
    # 사이트의 HTML/URL 구조가 변경되면 이 부분의 선택자 수정이 필요할 수 있습니다.
    anchors = soup.select(
        'a[href*="/Recruit/GI_Read/"], '
        'a[href*="/Recruit/GI_Read"], '
        'a[href*="GI_Read"]'
    )

    seen = set()
    for anchor in anchors:
        href = anchor.get("href", "").strip()
        link = urljoin(response.url, href)
        title = clean_text(anchor.get_text(" ", strip=True))

        if not href or not title or link in seen:
            continue

        # 링크의 상위 요소에서 기업명/공고 정보를 찾습니다.
        container = anchor
        for _ in range(5):
            if container.parent is None:
                break
            container = container.parent
            text = clean_text(container.get_text(" ", strip=True))
            if len(text) > len(title) + 2:
                break

        container_text = clean_text(container.get_text(" ", strip=True))
        company = "기업명 확인 필요"

        # 흔히 사용되는 기업명 클래스가 있으면 우선 활용합니다.
        company_tag = container.select_one(
            ".corp-name, .name, .company, .coName, .company-name"
        )
        if company_tag:
            company = clean_text(company_tag.get_text(" ", strip=True))
        else:
            # 회사명이 분리된 요소로 확인되지 않으면 임의로 추측하지 않습니다.
            company = "기업명 확인 필요"

        jobs.append({
            "site": "잡코리아",
            "title": title,
            "company": company,
            "link": link,
        })
        seen.add(link)

    return jobs


@app.route("/", methods=["GET", "POST"])
def index():
    keyword = ""
    jobs = []
    errors = []

    if request.method == "POST":
        keyword = clean_text(request.form.get("keyword", ""))

        if keyword:
            # 두 사이트를 각각 실행합니다. 한쪽이 실패해도 다른 쪽 결과는 표시합니다.
            for site_name, crawler in (
                ("인크루트", crawl_incruit),
                ("잡코리아", crawl_jobkorea),
            ):
                try:
                    jobs.extend(crawler(keyword))
                except requests.RequestException as exc:
                    errors.append(
                        f"{site_name} 검색 중 네트워크/접속 오류가 발생했습니다."
                    )
                except Exception:
                    errors.append(
                        f"{site_name} 검색 결과를 분석하지 못했습니다. "
                        "사이트의 HTML 구조가 변경되었을 수 있습니다."
                    )

    return render_template(
        "index.html",
        keyword=keyword,
        jobs=jobs,
        errors=errors,
    )


if __name__ == "__main__":
    app.run(debug=True)
