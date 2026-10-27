const MATH = {delimiters: [
  {left: '$$', right: '$$', display: true},
  {left: '$', right: '$', display: false}], throwOnError: false};

async function api(path, opts) {
  const r = await fetch(path, opts && {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(opts)});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ('Erreur ' + r.status));
  return data;
}

Vue.createApp({
  template: '#tpl',
  data: () => ({
    screen: 'home', home: null, session: null, summary: null, flipped: false, busy: false, error: '',
    chosen: [], includeAcquired: false, onlyAbbreviations: false, reviewAcquired: false,
    statuses: [
      {key: 'acquise', label: 'acquises', color: 'var(--acq)'},
      {key: 'validee', label: 'validées', color: 'var(--valid)'},
      {key: 'en_apprentissage', label: 'en apprentissage', color: 'var(--learn)'},
      {key: 'nouvelle', label: 'nouvelles', color: 'var(--new)'}],
  }),
  async mounted() {
    window.addEventListener('keydown', this.onKey);
    await this.loadHome();
  },
  methods: {
    async guard(fn) {
      this.error = '';
      try { return await fn(); } catch (e) { this.error = e.message; }
    },
    async renderMath() {
      await Vue.nextTick();
      const box = this.$refs.cardBox || this.$refs.sumBox;
      if (box) renderMathInElement(box, MATH);
      if (this.screen === 'home') renderMathInElement(this.$el, MATH);
    },
    async loadHome() {
      await this.guard(async () => { this.home = await api('/api/home'); this.screen = 'home'; });
      await this.renderMath();
    },
    async start() {
      await this.guard(async () => {
        this.session = await api('/api/sessions', {chapters: this.chosen, include_acquired: this.includeAcquired,
          only_abbreviations: this.onlyAbbreviations, review_acquired: this.reviewAcquired});
        await this.enter();
      });
    },
    async resume(id) {
      await this.guard(async () => { this.session = await api('/api/sessions/' + id); await this.enter(); });
    },
    async enter() {
      this.flipped = false;
      if (this.session.finished || !this.session.card) return this.showSummary();
      this.screen = 'review';
      await this.renderMath();
    },
    async flip() {
      if (this.flipped || !this.session.card) return;
      this.flipped = true;
      await this.renderMath();
    },
    async answer(correct) {
      if (!this.flipped || this.busy || !this.session.card) return;
      this.busy = true;
      await this.guard(async () => {
        this.session = await api('/api/sessions/' + this.session.id + '/answer',
          {card_id: this.session.card.id, correct});
        await this.enter();
      });
      this.busy = false;
    },
    async stop() {
      await this.guard(async () => {
        await api('/api/sessions/' + this.session.id + '/end', {});
        await this.showSummary();
      });
    },
    async showSummary() {
      this.summary = await api('/api/sessions/' + this.session.id + '/summary');
      this.screen = 'summary';
      await this.renderMath();
    },
    async goHome() { await this.loadHome(); },
    onKey(e) {
      if (this.screen !== 'review' || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.code === 'Space') { e.preventDefault(); this.flip(); }
      else if (this.flipped && e.key === '1') this.answer(false);
      else if (this.flipped && e.key === '2') this.answer(true);
    },
  },
}).mount('#app');
