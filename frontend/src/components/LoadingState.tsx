import styles from './LoadingState.module.css'

const COLUMN_CARD_COUNTS = [3, 2, 2]

export function LoadingState() {
  return (
    <div className={styles.board} aria-hidden="true">
      {COLUMN_CARD_COUNTS.map((cardCount, columnIndex) => (
        <div key={columnIndex} className={styles.column}>
          <div className={styles.columnHeader}>
            <div className={`${styles.bar} ${styles.label}`} />
            <div className={styles.badge} />
          </div>
          {Array.from({ length: cardCount }).map((_, cardIndex) => (
            <div key={cardIndex} className={styles.skeletonCard}>
              <div className={`${styles.bar} ${styles.wide}`} />
              <div className={`${styles.bar} ${styles.narrow}`} />
              <div className={styles.footerRow}>
                <div className={styles.pill} />
                <div className={styles.pill} />
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
