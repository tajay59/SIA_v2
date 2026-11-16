<script setup lang="ts">
/**
 * Footer = legacy SHOP Footer.vue, content and layout as-is (owner, 2026-11-16): CIMH name + street address +
 * contact (3/12), stay connected + write to us (2/12), national services (3/12), other resources (4/12); no
 * copyright line. Only accessibility kept on top: link names, 24 px targets, AA colours.
 */
import { mdiFacebook, mdiLinkedin, mdiOpenInNew, mdiSkype, mdiTwitter, mdiVimeo, mdiYoutube } from '@mdi/js'

const social = [
  { icon: mdiFacebook, label: 'Facebook', href: 'http://facebook.com/CIMHbb' },
  { icon: mdiTwitter, label: 'Twitter', href: 'http://twitter.com/CIMHbb' },
  { icon: mdiLinkedin, label: 'LinkedIn', href: 'https://www.linkedin.com/pub/cimh-barbados/a5/104/15b/en' },
  { icon: mdiVimeo, label: 'Vimeo', href: 'http://vimeo.com/cimhtv' },
  { icon: mdiYoutube, label: 'YouTube', href: 'https://www.youtube.com/user/CIMHTV' },
  { icon: mdiSkype, label: 'Skype', href: 'skype:cimhbb?chat' },
]
const services = [
  ['Antigua and Barbuda', 'http://www.antiguamet.com/'],
  ['Barbados', 'http://www.barbadosweather.org/'],
  ['Belize', 'http://www.hydromet.gov.bz/'],
  ['Cayman Islands', 'http://www.weather.gov.ky/portal/page?_pageid=4421,1&_dad=portal&_schema=PORTAL'],
  ['Dominica', 'http://www.weather.gov.dm/'],
  ['French Antilles', 'http://www.meteofrance.gp/previsions-meteo-antilles-guyane/animation/radar/antilles'],
  ['Guyana', 'http://www.hydromet.gov.gy/'],
  ['Jamaica: Hydro', 'http://waterresourcesauthority.com/'],
  ['Jamaica: Met', 'http://www.metservice.gov.jm/'],
  ['St. Kitts and Nevis', 'http://www.weather.kn/'],
  ['St. Lucia', 'http://www.slumet.gov.lc/'],
  ['Trinidad & Tobago', 'http://www.metoffice.gov.tt/'],
]
const resources = [
  ['DEWETRA', 'http://bb02.cimafoundation.org:8080/dewetra/'],
  ['SCOPE - Nowcasting', 'http://sigma.cptec.inpe.br/scope/'],
  ['CDEMA', 'http://www.cdema.org/'],
  ['RAMSDIS', 'http://rammb.cira.colostate.edu/ramsdis/online/rmtc.asp#Sector'],
  ['Center for Satellite Applications and Research (STAR)', 'http://www.star.nesdis.noaa.gov/smcd/emb/ff/HE_CA_3Hour.php'],
  ['National Centers for Environmental Prediction (NCEP)', 'http://www.ncep.noaa.gov/'],
  ['Hydrometeorological Prediction Center (HPC)', 'http://www.hpc.ncep.noaa.gov/'],
  ['Tropical Prediction Center/National Hurricane Center (TPC/NHC)', 'http://www.nhc.noaa.gov/'],
  ['Unisys Weather', 'http://weather.unisys.com/'],
]
const year = new Date().getFullYear()
// slim = flow pages (cart, requests, agreement): one contact line instead of the link directory.
defineProps<{ slim?: boolean }>()
</script>

<template>
  <footer v-if="slim" class="footer slim">
    <p class="slim-line">
      CIMH · <a href="tel:+12464251362">+1 (246) 425 1362/63</a> · <a href="mailto:info@cimh.edu.bb">info@cimh.edu.bb</a>
      <span class="copy-inline">© {{ year }} CIMH</span>
    </p>
  </footer>
  <footer v-else class="footer">
    <div class="inner">
      <section class="col c3">
        <h2 class="head">THE CARIBBEAN INSTITUTE FOR METEOROLOGY AND HYDROLOGY</h2>
        <address class="addr">Husbands<br />St James<br />Barbados BB23006</address>
        <h2 class="head">CONTACT</h2>
        <p class="line">Tel : +1 (246) 425 1362/63</p>
        <p class="line">Fax: +1 (246) 424 4733</p>
        <p class="line">Email: info@cimh.edu.bb</p>
        <p class="line">
          Website:
          <a class="site" href="https://cimh.edu.bb/" target="_blank" rel="noopener">CIMH <v-icon :icon="mdiOpenInNew" size="14" /></a>
        </p>
      </section>

      <section class="col c2">
        <h2 class="head head-sub">STAY CONNECTED</h2>
        <p class="line">Follow us on these networks:</p>
        <div class="social">
          <v-btn
            v-for="s in social"
            :key="s.label"
            :icon="s.icon"
            :href="s.href"
            target="_blank"
            rel="noopener"
            variant="plain"
            density="compact"
            :aria-label="s.label"
          />
        </div>
        <h2 class="head spaced">WRITE TO US</h2>
        <p class="line">P.O. Box 130</p>
        <p class="line">Bridgetown</p>
        <p class="line">Barbados</p>
      </section>

      <section class="col c3">
        <h2 class="head list-head">HYDROLOGICAL &amp; METEOROLOGICAL SERVICES</h2>
        <ul class="links">
          <li v-for="[name, href] in services" :key="name"><a :href="href" target="_blank" rel="noopener">{{ name }}</a></li>
        </ul>
      </section>

      <section class="col c4">
        <h2 class="head list-head">OTHER RESOURCES</h2>
        <ul class="links">
          <li v-for="[name, href] in resources" :key="name"><a :href="href" target="_blank" rel="noopener">{{ name }}</a></li>
        </ul>
      </section>
    </div>
  </footer>
</template>

<style scoped>
.footer.slim {
  padding: var(--sp-4);
}
.slim-line {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-2);
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.copy-inline {
  margin-left: auto;
}

/* Legacy: background colour, 1 px divider on top, a 1300 px row of 3/2/3/4 columns, generous bottom space. */
.footer:not(.slim) {
  background: rgb(var(--v-theme-background));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 0 var(--sp-3) 60px;
}
.inner {
  max-width: 1300px;
  margin: 0 auto 60px;
  display: grid;
  grid-template-columns: 3fr 2fr 3fr 4fr;
  gap: 0 var(--sp-6);
  text-align: left;
}
@media (max-width: 959.98px) {
  .inner {
    grid-template-columns: 1fr;
    padding: var(--sp-5, 20px);
  }
}
.head {
  font-size: 16px;
  line-height: 24px;
  font-weight: 700;
  margin: 40px 0 0;
}
.head:not(:first-child) {
  margin-top: 0;
}
.head.spaced {
  margin-top: 40px;
}
.head.list-head {
  margin-bottom: var(--sp-5, 20px);
}
.addr {
  font-style: normal;
  font-size: 12px;
  line-height: 20px;
  margin: var(--sp-5, 20px) 0;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.line {
  margin: 0;
  font-size: 12px;
  line-height: 24px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.site {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-height: 24px;
  margin: var(--sp-2) 0;
}
.social {
  display: flex;
  flex-wrap: wrap;
  margin: var(--sp-2) 0;
}
.links {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 12px;
}
.links a,
.site {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  display: inline-block;
  min-height: 24px;
  line-height: 24px;
}
.links a:hover,
.site:hover {
  text-decoration: underline;
}
</style>
