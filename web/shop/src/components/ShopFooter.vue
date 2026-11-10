<script setup lang="ts">
/** Footer (legacy SHOP Footer.vue): CIMH contact, stay connected + write to us, national services, resources. */
import { mdiFacebook, mdiLinkedin, mdiTwitter, mdiVimeo, mdiYoutube } from '@mdi/js'

const social = [
  { icon: mdiFacebook, label: 'Facebook', href: 'https://facebook.com/CIMHbb' },
  { icon: mdiTwitter, label: 'X (Twitter)', href: 'https://twitter.com/CIMHbb' },
  { icon: mdiLinkedin, label: 'LinkedIn', href: 'https://www.linkedin.com/pub/cimh-barbados/a5/104/15b/en' },
  { icon: mdiVimeo, label: 'Vimeo', href: 'https://vimeo.com/cimhtv' },
  { icon: mdiYoutube, label: 'YouTube', href: 'https://www.youtube.com/user/CIMHTV' },
]
const services = [
  ['Antigua and Barbuda', 'http://www.antiguamet.com/'],
  ['Barbados', 'http://www.barbadosweather.org/'],
  ['Belize', 'http://www.hydromet.gov.bz/'],
  ['Cayman Islands', 'http://www.weather.gov.ky/'],
  ['Dominica', 'http://www.weather.gov.dm/'],
  ['French Antilles', 'http://www.meteofrance.gp/'],
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
  ['RAMSDIS', 'http://rammb.cira.colostate.edu/ramsdis/online/rmtc.asp'],
]
const year = new Date().getFullYear()
</script>

<template>
  <footer class="footer">
    <div class="inner">
      <section>
        <h2 class="head">The Caribbean Institute for Meteorology and Hydrology</h2>
        <h3 class="sub">Contact</h3>
        <ul class="plain">
          <li>Tel: <a href="tel:+12464251362">+1 (246) 425 1362/63</a></li>
          <li>Fax: +1 (246) 424 4733</li>
          <li>Email: <a href="mailto:info@cimh.edu.bb">info@cimh.edu.bb</a></li>
          <li>Website: <a href="https://cimh.edu.bb/" target="_blank" rel="noopener">cimh.edu.bb</a></li>
        </ul>
      </section>
      <section>
        <h2 class="head">Stay connected</h2>
        <div class="social">
          <v-btn
            v-for="s in social"
            :key="s.label"
            :icon="s.icon"
            :href="s.href"
            target="_blank"
            rel="noopener"
            variant="text"
            size="small"
            :aria-label="s.label"
          />
        </div>
        <h3 class="sub">Write to us</h3>
        <address class="plain">P.O. Box 130<br />Bridgetown<br />Barbados</address>
      </section>
      <section>
        <h2 class="head">Hydrological &amp; meteorological services</h2>
        <ul class="links two">
          <li v-for="[name, href] in services" :key="name"><a :href="href" target="_blank" rel="noopener">{{ name }}</a></li>
        </ul>
      </section>
      <section>
        <h2 class="head">Other resources</h2>
        <ul class="links">
          <li v-for="[name, href] in resources" :key="name"><a :href="href" target="_blank" rel="noopener">{{ name }}</a></li>
        </ul>
      </section>
    </div>
    <p class="copy">© {{ year }} CIMH. All rights reserved.</p>
  </footer>
</template>

<style scoped>
.footer {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  padding: var(--sp-12, 48px) var(--sp-4) var(--sp-6);
}
.inner {
  max-width: 1200px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1.2fr 1fr 1.6fr 1fr;
  gap: var(--sp-8);
}
@media (max-width: 959px) {
  .inner {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 599.98px) {
  .inner {
    grid-template-columns: 1fr;
  }
}
.head {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin: 0 0 var(--sp-3);
}
.sub {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin: var(--sp-4) 0 var(--sp-2);
  opacity: 0.72;
}
.plain,
.links {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 13px;
  font-style: normal;
  line-height: 1.8;
  /* Muted text by colour, not opacity: opacity also faded the links below AA contrast. */
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.links.two {
  columns: 2;
  column-gap: var(--sp-4);
}
.links a,
.plain a {
  text-decoration: none;
  /* Stacked links are tap targets: at least 24 px tall (WCAG 2.5.8); 13 px x 1.8 was 23.4 px. */
  display: inline-block;
  min-height: 24px;
  line-height: 24px;
}
.links a:hover,
.plain a:hover {
  text-decoration: underline;
}
.social {
  display: flex;
  gap: 2px;
  margin-left: -8px;
}
.copy {
  max-width: 1200px;
  margin: var(--sp-8) auto 0;
  padding-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 12px;
  opacity: 0.72;
}
</style>
