import buttons from '../styles/buttons.module.css'
import styles from './ConnectScreen.module.css'

interface ConnectScreenProps {
  /** 'invalid' means a token was present and rejected; worth saying, or the
   * link looks like it failed silently. */
  reason: 'missing' | 'invalid'
  onRetry: () => void
}

/** Shown when the browser has no valid dashboard token. There is no login
 * form: the bot is the only thing that hands out a board link. */
export function ConnectScreen({ reason, onRetry }: ConnectScreenProps) {
  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <div className={styles.mark} aria-hidden="true">
          <BotIcon />
        </div>

        <h1 className={styles.title}>Connect your Telegram</h1>
        <p className={styles.subtitle}>
          Your board is private. Open it with the personal link the bot gives you — no
          sign-up, no password.
        </p>

        {reason === 'invalid' && (
          <p className={styles.notice}>
            That link is no longer valid. Ask the bot for a fresh one.
          </p>
        )}

        <ol className={styles.steps}>
          <li className={styles.step}>
            <span className={styles.stepNumber}>1</span>
            <span>Open your AI Task Bot chat in Telegram.</span>
          </li>
          <li className={styles.step}>
            <span className={styles.stepNumber}>2</span>
            <span>
              Send <span className={styles.command}>/dashboard</span> to the bot.
            </span>
          </li>
          <li className={styles.step}>
            <span className={styles.stepNumber}>3</span>
            <span>Tap the link it replies with — this page will load your tasks.</span>
          </li>
        </ol>

        <div className={styles.actions}>
          <button type="button" className={buttons.secondary} onClick={onRetry}>
            I&apos;ve opened the link — check again
          </button>
        </div>

        <p className={styles.footnote}>
          The link signs in this browser only. Anyone you forward it to can see your
          board, so keep it to yourself.
        </p>
      </div>
    </div>
  )
}

function BotIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="3" y="6" width="10" height="7" rx="2.5" stroke="white" strokeWidth="1.4" />
      <path d="M8 6V3.5" stroke="white" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="8" cy="2.5" r="1" fill="white" />
      <circle cx="6" cy="9.5" r="1" fill="white" />
      <circle cx="10" cy="9.5" r="1" fill="white" />
    </svg>
  )
}
