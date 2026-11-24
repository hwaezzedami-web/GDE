package com.bouchra.love;

import android.view.View;

/** One screen of the bottom navigation bar. */
public interface Tab {
    View build();

    /** Redraws data (e.g. after the partner changed a shared list). */
    void refresh();

    /** Called when the tab is left or the app goes to the background. */
    void hide();
}
