#!/bin/bash
# Auto Job Application Pipeline
# Orchestrates all flows: Scrape → Enrich → Screen → (Apply)
#
# Usage:
#   ./scripts/run_pipeline.sh                    # Run full pipeline (no apply)
#   ./scripts/run_pipeline.sh --mode full        # Run full pipeline (no apply)
#   ./scripts/run_pipeline.sh --mode scrape      # Scrape only
#   ./scripts/run_pipeline.sh --mode enrich      # Enrich only
#   ./scripts/run_pipeline.sh --mode screen      # Screen only
#   ./scripts/run_pipeline.sh --mode apply       # Apply only (future)
#   ./scripts/run_pipeline.sh --with-apply       # Run full pipeline with apply
#   ./scripts/run_pipeline.sh --dry-run          # Preview without changes
#   ./scripts/run_pipeline.sh --help             # Show help

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Resolve script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Load environment
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Default values
MODE="full"
WITH_APPLY=false
DRY_RUN=false
SCRAPE_LIMIT=10
ENRICH_LIMIT=20
SCREEN_LIMIT=20
APPLY_LIMIT=5
SCREEN_THRESHOLD=0.6

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --with-apply)
            WITH_APPLY=true
            shift
            ;;
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --scrape-limit)
            SCRAPE_LIMIT="$2"
            shift 2
            ;;
        --enrich-limit)
            ENRICH_LIMIT="$2"
            shift 2
            ;;
        --screen-limit)
            SCREEN_LIMIT="$2"
            shift 2
            ;;
        --apply-limit)
            APPLY_LIMIT="$2"
            shift 2
            ;;
        --threshold)
            SCREEN_THRESHOLD="$2"
            shift 2
            ;;
        --help|-h)
            echo "Auto Job Application Pipeline"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --mode MODE         Pipeline mode: full, scrape, enrich, screen, apply"
            echo "  --with-apply        Include apply step in full mode (default: false)"
            echo "  --dry-run, -n       Preview without making changes"
            echo "  --scrape-limit N    Max jobs to scrape (default: 10)"
            echo "  --enrich-limit N    Max jobs to enrich (default: 20)"
            echo "  --screen-limit N    Max jobs to screen (default: 20)"
            echo "  --apply-limit N     Max jobs to apply (default: 5)"
            echo "  --threshold N       AI screening threshold (default: 0.6)"
            echo "  --help, -h          Show this help"
            echo ""
            echo "Modes:"
            echo "  full      Run: Scrape → Enrich → Screen (default)"
            echo "  scrape    Run scraper only"
            echo "  enrich    Run enricher only"
            echo "  screen    Run AI screening only"
            echo "  apply     Run Easy Apply only (future)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Print banner
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}        ${GREEN}AUTO JOB APPLICATION PIPELINE${NC}                         ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Mode:           ${YELLOW}$MODE${NC}"
echo -e "With Apply:     ${YELLOW}$WITH_APPLY${NC}"
echo -e "Dry Run:        ${YELLOW}$DRY_RUN${NC}"
echo ""

# Track results
SCRAPE_RESULT=""
ENRICH_RESULT=""
SCREEN_RESULT=""
APPLY_RESULT=""

# Function to run scraper
run_scrape() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}FLOW 1: SCRAPE${NC} - Discovering new jobs..."
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would run: ./scripts/run_playwright_scraper.sh --limit $SCRAPE_LIMIT"
        SCRAPE_RESULT="DRY_RUN"
    else
        if ./scripts/run_playwright_scraper.sh --limit "$SCRAPE_LIMIT"; then
            SCRAPE_RESULT="SUCCESS"
        else
            SCRAPE_RESULT="FAILED"
            echo -e "${RED}Scraper failed!${NC}"
        fi
    fi
}

# Function to run enricher
run_enrich() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}FLOW 2: ENRICH${NC} - Extracting job details..."
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would run: ./scripts/run_playwright_enricher.sh --limit $ENRICH_LIMIT"
        ENRICH_RESULT="DRY_RUN"
    else
        if ./scripts/run_playwright_enricher.sh --limit "$ENRICH_LIMIT"; then
            ENRICH_RESULT="SUCCESS"
        else
            ENRICH_RESULT="FAILED"
            echo -e "${RED}Enricher failed!${NC}"
        fi
    fi
}

# Function to run AI screening
run_screen() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}FLOW 3: AI SCREEN${NC} - Scoring job fit..."
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would run: ./scripts/run_ai_screening.sh --limit $SCREEN_LIMIT --threshold $SCREEN_THRESHOLD"
        SCREEN_RESULT="DRY_RUN"
    else
        if ./scripts/run_ai_screening.sh --limit "$SCREEN_LIMIT" --threshold "$SCREEN_THRESHOLD"; then
            SCREEN_RESULT="SUCCESS"
        else
            SCREEN_RESULT="FAILED"
            echo -e "${RED}AI Screening failed!${NC}"
        fi
    fi
}

# Function to run Easy Apply
run_apply() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}FLOW 4: APPLY${NC} - Submitting applications..."
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [ ! -f "./scripts/run_easy_apply.sh" ]; then
        echo -e "${YELLOW}[NOT IMPLEMENTED]${NC} Easy Apply script not yet created"
        APPLY_RESULT="NOT_IMPLEMENTED"
    elif [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would run: ./scripts/run_easy_apply.sh --limit $APPLY_LIMIT"
        APPLY_RESULT="DRY_RUN"
    else
        if ./scripts/run_easy_apply.sh --limit "$APPLY_LIMIT"; then
            APPLY_RESULT="SUCCESS"
        else
            APPLY_RESULT="FAILED"
            echo -e "${RED}Easy Apply failed!${NC}"
        fi
    fi
}

# Function to show database stats
show_stats() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}DATABASE STATUS${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    python3 scripts/cleanup_jobs.py --stats
}

# Run pipeline based on mode
case $MODE in
    full)
        run_scrape
        run_enrich
        run_screen
        if [ "$WITH_APPLY" = true ]; then
            run_apply
        fi
        ;;
    scrape)
        run_scrape
        ;;
    enrich)
        run_enrich
        ;;
    screen)
        run_screen
        ;;
    apply)
        run_apply
        ;;
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        exit 1
        ;;
esac

# Show summary
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}                    ${GREEN}PIPELINE SUMMARY${NC}                          ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ -n "$SCRAPE_RESULT" ]; then
    case $SCRAPE_RESULT in
        SUCCESS) echo -e "  SCRAPE:   ${GREEN}✅ SUCCESS${NC}" ;;
        FAILED)  echo -e "  SCRAPE:   ${RED}❌ FAILED${NC}" ;;
        DRY_RUN) echo -e "  SCRAPE:   ${YELLOW}🔍 DRY RUN${NC}" ;;
    esac
fi

if [ -n "$ENRICH_RESULT" ]; then
    case $ENRICH_RESULT in
        SUCCESS) echo -e "  ENRICH:   ${GREEN}✅ SUCCESS${NC}" ;;
        FAILED)  echo -e "  ENRICH:   ${RED}❌ FAILED${NC}" ;;
        DRY_RUN) echo -e "  ENRICH:   ${YELLOW}🔍 DRY RUN${NC}" ;;
    esac
fi

if [ -n "$SCREEN_RESULT" ]; then
    case $SCREEN_RESULT in
        SUCCESS) echo -e "  SCREEN:   ${GREEN}✅ SUCCESS${NC}" ;;
        FAILED)  echo -e "  SCREEN:   ${RED}❌ FAILED${NC}" ;;
        DRY_RUN) echo -e "  SCREEN:   ${YELLOW}🔍 DRY RUN${NC}" ;;
    esac
fi

if [ -n "$APPLY_RESULT" ]; then
    case $APPLY_RESULT in
        SUCCESS)         echo -e "  APPLY:    ${GREEN}✅ SUCCESS${NC}" ;;
        FAILED)          echo -e "  APPLY:    ${RED}❌ FAILED${NC}" ;;
        DRY_RUN)         echo -e "  APPLY:    ${YELLOW}🔍 DRY RUN${NC}" ;;
        NOT_IMPLEMENTED) echo -e "  APPLY:    ${YELLOW}📅 NOT IMPLEMENTED${NC}" ;;
    esac
fi

echo ""

# Show database stats after pipeline
show_stats

echo ""
echo -e "${GREEN}Pipeline complete!${NC}"
