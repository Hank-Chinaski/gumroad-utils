import json
import logging
import random
import time
from datetime import date, datetime
from typing import TYPE_CHECKING

import humanize
from pathlib3x import Path
from rich.progress import Progress as RichProgress

from gumroad_utils.misc.session import detect_redirect

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, PageElement

    from gumroad_utils.misc.cache import Cache, DownloadStatus
    from gumroad_utils.misc.session import GumroadSession

__all__ = ["GumroadScrapper"]

_ARCHIVES_EXT = {"rar", "zip"}


# https://www.xormedia.com/string-truncate-middle-with-ellipsis/
def shorten(s: str, n: int = 40) -> str:
    if len(s) <= n:
        return s

    n_2 = int(n) / 2 - 3
    n_1 = n - n_2 - 3

    return "{0}..{1}".format(s[:n_1], s[-n_2:])


class GumroadScrapper:
    def __init__(
        self, cache: "Cache", session: "GumroadSession", root_folder: Path, product_folder_tmpl: str
    ) -> None:
        self._cache = cache
        self._session = session
        self._root_folder = root_folder
        self._product_folder_tmpl = product_folder_tmpl
        self._logger = logging.getLogger()

    # I/O

    def load_cache(self, file_path: Path) -> None:
        self._cache.load_cache(file_path)
        self._logger.debug("Cache has been loaded.")

    def save_cache(self, file_path: Path) -> None:
        self._cache.save_cache(file_path)
        self._logger.debug("Cache has been saved.")

    # Pages - Library

    def scrape_library(self) -> None:
        soup = self._session.get_soup("/library", short=True)
        detect_redirect(soup)

        script = soup.find(
            "script",
            attrs={
                "class": "js-react-on-rails-component",
                "data-component-name": "LibraryPage",
            },
        )
        script = json.loads(script.string)

        self._logger.info("Found %s products in your library.", len(script["results"]))
        for result in script["results"]:
            self.scrap_product_page(result["purchase"]["download_url"])

    # Pages - Product content

    def scrap_product_page(self, url: str) -> None:
        if url.isalnum():
            url = self._session.base_url + url

        self._logger.info("Scrapping %r...", url)

        soup = self._session.get_soup(url)
        detect_redirect(soup)

        product_creator = soup.select_one(".paragraphs:nth-child(1) > .stack:nth-child(3) a").string
        product_name = soup.select_one("header h1").string
        recipe_link = soup.select_one(".paragraphs:nth-child(1) > .stack:nth-child(2) a", href=True)["href"]

        purchase_date, price = self._scrap_recipe_page(recipe_link)

        product_folder_name = self._product_folder_tmpl.format(
            product_name=product_name,
            purchase_date=purchase_date,
            price=price,
        )
        product_folder: "Path" = self._root_folder / product_creator / product_folder_name

        # NOTE(obsessedcake): We might be able to download everything in a single zip archive.
        #   Download all -> Download as ZIP
        for action in soup.select(".actions button"):
            if "ZIP" not in action.find(text=True):
                continue

            # NOTE(obsessedcake): Creators can publish an single archive as a content for the product.
            #   If it's a case, let's download in a normal way.
            if self._content_is_archive(soup):
                break

            self._logger.info(
                "Downloading %r product of %r creator as a zip archive.",
                product_name,
                product_creator
            )

            zip_url = url.replace("/d/", "/zip/")
            output = product_folder.append_suffix(".zip")

            self._fancy_download_file(zip_url, Path("/"), output, short_desc=True)
            return

        self._logger.info("Downloading %r product of %r creator...", product_name, product_creator)

        files_count = len(soup.select(".js-file-list-element"))
        folders_count = len(soup.select("div[role=treeitem]")) - files_count
        if folders_count < 0:
            folders_count = 0

        self._logger.info("Found %r folder(s) and %r file(s) in total.", folders_count, files_count)

        self._traverse_tree(soup.select_one("div[role=tree]"), Path("/"), product_folder)

    def _content_is_archive(self, product_page_soup: "BeautifulSoup") -> bool:
        tree_elements = product_page_soup.select(".js-file-list-element")
        if len(tree_elements) > 1:
            return False

        file_type = tree_elements[0].select_one("li:nth-child(1)").string.strip().lower()
        return file_type in _ARCHIVES_EXT

    def _traverse_tree(self, tree_root: "PageElement", tree_path: Path, parent_folder: Path) -> None:
        self._logger.info("Downloading '%s'...", tree_path)

        first_tree_item = tree_root.find_next("div", attrs={"role": "treeitem"})
        if not first_tree_item:
            self._logger.warning("'%s' appeared to be empty!", tree_path)
            return

        # NOTE(obsessedcake): 'select' and 'find_all_next' doesn't support non-recursive search.
        #   So I came up with this ugly code.
        other_tree_items = first_tree_item.find_next_siblings("div", attrs={"role": "treeitem"})
        if other_tree_items:
            tree_items = [first_tree_item, *other_tree_items]
        else:
            tree_items = [first_tree_item]

        files: list["PageElement"] = []
        folders: list["PageElement"] = []

        for tree_item in tree_items:
            if "js-file-list-element" in tree_item.get("class", []):
                files.append(tree_item)
            else:
                folders.append(tree_item)

        self._logger.debug("Found %r files in '%s' folder.", len(files), tree_path)
        self._logger.debug("Found %r folders in '%s' folder.", len(folders), tree_path)

        for file_idx, file in enumerate(files):
            file_type = file.select_one("li:nth-child(1)").string.lower()
            file_name = file.select_one("h4").string
            file_url = self._session.base_url + file.select_one("a", href=True)["href"]

            file_path = (parent_folder / file_name).with_suffix("." + file_type)
            self._fancy_download_file(
                file_url,
                tree_path,
                file_path,
                len(files),  # files_total_count
                file_idx + 1,  # file_idx
            )

            sleep_time = random.uniform(0.1, 2.0)
            self._logger.debug("Sleepping for %s seconds.", sleep_time)
            time.sleep(sleep_time)

        for folder in folders:
            folder_name = folder.select_one("h4").string
            folder_content = folder.select_one("div[role=group]")

            self._traverse_tree(folder_content, tree_path / folder_name, parent_folder / folder_name)

    # Pages - Recipe

    def _scrap_recipe_page(self, url: str) -> tuple[date, str]:
        soup = self._session.get_soup(url)

        purchase_date = soup.select_one(".main > div:nth-child(1) > p").string.strip()
        purchase_date = datetime.strptime(purchase_date, "%B %d, %Y").date()  # February 14, 2022\n

        payment_info = soup.select_one(".main > div:nth-child(1) > div").string
        price = payment_info.strip().split("\n")[0]  # \n$9.99\n— VISA *0000

        return purchase_date, price

    # File downloader

    def _fancy_download_file(
        self,
        url: str,
        tree_path: Path,
        file_path: Path,
        files_total_count: int = 0,
        file_idx: int = 0,
        *,
        short_desc=False
    ) -> None:
        *_, product_id, file_id = url.split("/")
        if product_id == "zip":
            product_id, file_id = file_id, product_id

        tree_file_path = tree_path / file_path.name

        if self._cache.is_file_cached(product_id, file_id):
            self._logger.debug("'%s' is already downloaded! Skipping.", tree_file_path)
            return

        response = self._session.get(url, stream=True)
        response.raise_for_status()

        total_size_in_bytes = int(response.headers.get('content-length', 0))
        if total_size_in_bytes == 0:
            self._logger.warning("Failed to download '%s' file, received zero content length!", tree_file_path)
            return

        human_size = humanize.naturalsize(total_size_in_bytes)
        if short_desc:
            task_desc = f"Downloading {human_size} file..."
        else:
            task_desc = f"[{file_idx}/{files_total_count}] Downloading '{shorten(file_path.name)}' file ({human_size})..."

        file_path.parent.mkdir(parents=True, exist_ok=True)

        with RichProgress(expand=True, transient=True) as progress:  # Fit logs and disappear after successful download.
            task = progress.add_task(task_desc, total=total_size_in_bytes)

            with file_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=4096):  # 4kb
                    if chunk:  # filter out keep-alive new chunks
                        progress.advance(task, len(chunk))
                        file.write(chunk)

        self._cache.cache_file(product_id, file_id)
