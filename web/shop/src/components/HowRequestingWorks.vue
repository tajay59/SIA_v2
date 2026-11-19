<script setup lang="ts">
/**
 * "How requesting works": the four steps that make this an institute store and not a webshop (approved
 * account, request without prices, quote, signed agreement). `strip` = the home section (steps side by side
 * on wide screens); `list` = the short vertical form used beside a product. The order is the information,
 * so the steps are numbered. Facts only (PRODUCT.md): no figures beyond the 30-day quote and the usual
 * two working days for approval. `band` = home masthead: one short line per step (owner: less text on home).
 */
withDefaults(defineProps<{ variant?: 'strip' | 'list' | 'band'; skipAccount?: boolean }>(), { variant: 'strip', skipAccount: false })

const STEPS = [
  {
    key: 'account',
    title: 'Create an account',
    short: 'Verify your email. CIMH approves the account.',
    text: 'Verify your email. A CIMH administrator then approves the account, usually within two working days.',
  },
  {
    key: 'request',
    title: 'Send a request',
    short: 'Add items to your cart and send it. No prices, no online payment.',
    text: 'Add what you need to the cart and send it. No prices are shown and nothing is paid online.',
  },
  {
    key: 'quote',
    title: 'Review the quote',
    short: 'CIMH emails you a quote with every price and the total, valid for 30 days.',
    text: 'CIMH prices every item, from its own stock or from a supplier, with the estimated shipping and the total. The quote is valid for 30 days.',
  },
  {
    key: 'sign',
    title: 'Sign and receive',
    short: 'Sign the agreement, upload it, and the items ship.',
    text: 'Download the agreement, sign it and upload the copy, or cancel the request. CIMH ships its stock items; suppliers ship theirs straight to you, each with a tracking link.',
  },
] as const
</script>

<template>
  <ol class="steps" :class="variant">
    <li v-for="s in STEPS.filter((x) => !(skipAccount && x.key === 'account'))" :key="s.key" class="step">
      <span class="step-title">{{ s.title }}</span>
      <span class="step-text">{{ variant === 'band' ? s.short : s.text }}</span>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
  counter-reset: step;
  display: grid;
  gap: var(--sp-6);
}
.step {
  counter-increment: step;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  min-width: 0;
}
.step::before {
  content: counter(step);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
}
.step-title {
  font-weight: 600;
}
.step-text {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* Home: four columns under one rule; the number sits on the rule like a tick on a scale. */
.strip {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.strip .step {
  padding-top: var(--sp-4);
}
.strip .step::before {
  font-size: 22px;
  line-height: 30px;
}
.strip .step::after {
  content: '';
  position: absolute;
  top: -1px;
  left: 0;
  width: 32px;
  height: 2px;
  background: rgb(var(--v-theme-primary));
}
.strip .step-title {
  font-size: 18px;
  line-height: 26px;
}
.strip .step-text {
  font-size: 15px;
  line-height: 24px;
  max-width: 34ch;
}

/* Home band: one path. Each step is a numbered node; a rule runs from node to node, so the four read as a
   sequence, not four cards. Phones: the path runs down the left edge. */
.band {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-6);
}
.band .step::before {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  font-size: 18px;
  font-weight: 700;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 6px rgb(var(--v-theme-surface-variant));
  margin-bottom: var(--sp-3);
  position: relative;
  z-index: 1;
}
.band .step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 21px;
  left: 44px;
  right: calc(-1 * var(--sp-6));
  height: 2px;
  background: rgb(var(--v-theme-primary));
  opacity: 0.5;
}
.band .step-title {
  font-size: 17px;
  line-height: 24px;
}
.band .step-text {
  font-size: 15px;
  line-height: 22px;
  max-width: 30ch;
}
@media (max-width: 759.98px) {
  .band {
    grid-template-columns: 1fr;
    gap: var(--sp-5, 20px);
  }
  .band .step {
    padding-left: 56px;
    min-height: 44px;
  }
  .band .step::before {
    position: absolute;
    left: 0;
    top: 0;
    width: 36px;
    height: 36px;
    font-size: 15px;
    margin: 0;
  }
  .band .step:not(:last-child)::after {
    top: 36px;
    left: 17px;
    right: auto;
    bottom: calc(-1 * var(--sp-5, 20px));
    width: 2px;
    height: auto;
  }
}

/* Beside a product: numbers in a left gutter. */
.list {
  gap: var(--sp-3);
}
.list .step {
  padding-left: 28px;
}
.list .step::before {
  position: absolute;
  left: 0;
  top: 0;
  font-size: 14px;
  line-height: 22px;
}
.list .step-title {
  font-size: 14px;
  line-height: 22px;
}
.list .step-text {
  font-size: 13px;
  line-height: 20px;
}
</style>
