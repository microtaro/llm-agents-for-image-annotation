// Where a plan is made, as a button (user 2026-10-28: with no plan the right showed the images
// only): the left's field, unfolded, the cursor in it, as a plan is made by asking the steward.
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { focusAsk } from "@/lib/talk";
import { useSideLayout } from "@/lib/viewState";

export function AskSteward() {
  const [layout, setLayout] = useSideLayout();
  return (
    <Button
      size="small"
      onClick={() => {
        if (layout.folded) setLayout({ folded: false });
        setTimeout(focusAsk, 0);
      }}
    >
      {t("decide.noPlan.ask")}
    </Button>
  );
}
