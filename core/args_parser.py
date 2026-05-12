import argparse
def parse_args():
    parser = argparse.ArgumentParser(
        description="Coffeeshops scraper from Google Maps — Browser-based automation tool"
    )
    parser.add_argument(
        "--scrape-places",
        action="store_true",
        help="Jalankan job scraping data tempat sekali"
    )
    parser.add_argument(
        "--scrape-reviews",
        action="store_true",
        help="Jalankan job scraping ulasan sekali"
    )
    parser.add_argument(
        "--sort",
        default="asc",
        help="Jalankan job scraping ulasan sekali"
    )
    parser.add_argument(
        "--analyze-sentiment",
        action="store_true",
        help="Jalankan job analisis sentimen ulasan"
    )
    parser.add_argument(
        "--scrape-places-queue",
        action="store_true",
        help="Jalankan job scraping tempat dari antrian"
    )
    return parser.parse_args()
