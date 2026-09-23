// Product name, links and logo template. The one place to change on a rename:
// index.html and manifest.webmanifest are generated from this file by the
// brand plugin in vite.config.js, and translations get {{brand}} from here.
//
// Keep this module free of framework and environment imports - the Vite
// config and the brand gate load it directly.
//
// Technical names (localStorage keys, API paths) are contracts with stored
// data and do not belong here.

export const BRAND = Object.freeze({
  name: 'Holma',
  // Lower-case name used for download file names and the backend container
  // (docker-compose names it `${slug}-backend`).
  slug: 'holma',
  tagline: 'Automated Multi-Source Backup Manager',
  description:
    'Self-hosted backup manager for 35 standard sources — NAS, Git, databases, cloud storage, Docker and Supabase.',
  repoUrl: 'https://github.com/hehljo/Holma',
  // Logo template. Swap the file, keep the path.
  logoMark: '/logo-mark.png',
  themeColor: '#071b4a',
  backgroundColor: '#f9fafb',
})
