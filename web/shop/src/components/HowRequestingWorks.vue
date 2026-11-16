<script setup lang="ts">
/**
 * "How requesting works": the four steps that make this an institute store and not a webshop (approved
 * account, request without prices, quote, signed agreement). `strip` = the home section (steps side by side
 * on wide screens); `list` = the short vertical form used beside a product. The order is the information,
 * so the steps are numbered. Facts only (PRODUCT.md): no figures beyond the 30-day quote and the usual
 * two working days for approval.
 */
withDefaults(defineProps<{ variant?: 'strip' | 'list'; skipAccount?: boolean }>(), { variant: 'strip', skipAccount: false })

const STEPS = [
  {
    key: 'account',
    title: 'Create an account',
    text: 'Verify your email. A CIMH administrator then approves the account, usually within two working days.',
  },
  {
    key: 'request',
    title: 'Send a request',
    text: 'Add what you need to the cart and send it. No prices are shown and nothing is paid online.',
  },
  {
    key: 'quote',
    title: 'Review the quote',
    text: 'CIMH emails you a quote, valid for 30 days. For items CIMH holds, you choose between CIMH stock and a supplier order.',
  },
  {
    key: 'sign',
    title: 'Sign and receive',
    text: 'Download the agreement, sign it and upload the copy. CIMH ships stock items; supplier items come straight to you.',
  },
] as const
</script>

<template>
  <ol class="steps" :class="variant">
    <li v-for="s in STEPS.filter((x) => !(skipAccount && x.key === 'account'))" :key="s.key" class="step">
      <span class="step-title">{{ s.title }}</span>
      <span class="step-text">{{ s.text }}</span>
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
