"""
Product name and links shown to people: notification titles, e-mail headers,
chat footers. The one place to change on a rename.

Technical identifiers that happen to carry the old name (database file, lock
and log paths, the credential salt, temp prefixes) are contracts with stored
data and deployments and deliberately do not come from here.
"""

BRAND_NAME = 'Holma'
BRAND_TAGLINE = 'Automated Multi-Source Backup Manager'
BRAND_REPO_URL = 'https://github.com/hehljo/Holma'
# Raw URL of the logo template the frontend also uses; swap the file, not this.
BRAND_ICON_URL = 'https://raw.githubusercontent.com/hehljo/Holma/main/frontend/public/logo-mark.png'
