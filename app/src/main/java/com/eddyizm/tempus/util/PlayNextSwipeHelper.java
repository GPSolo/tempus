package com.eddyizm.tempus.util;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.media3.session.MediaBrowser;
import androidx.recyclerview.widget.ItemTouchHelper;
import androidx.recyclerview.widget.RecyclerView;

import com.eddyizm.tempus.R;
import com.eddyizm.tempus.service.MediaManager;
import com.eddyizm.tempus.subsonic.models.Child;
import com.google.common.util.concurrent.ListenableFuture;

import java.util.Map;
import java.util.WeakHashMap;
import java.util.function.Function;
import java.util.function.Supplier;

public final class PlayNextSwipeHelper {
    private PlayNextSwipeHelper() {}

    // One helper per recycler. Fragments re-observe live data and recreate adapters, which would
    // otherwise stack ItemTouchHelpers; replacing keeps the swipe bound to the current adapter.
    private static final Map<RecyclerView, ItemTouchHelper> ATTACHED = new WeakHashMap<>();

    // Right-swipe a song row to queue it as the next track. The row snaps back after the swipe;
    // the enqueue itself happens immediately. It goes through MediaManager.enqueue(..., true, true)
    // so the "Preserve Play Next order" setting applies. The browser future and the item lookup are
    // read lazily at swipe time because the fragments only set the media browser in onStart.
    public static void attach(
            @NonNull RecyclerView recyclerView,
            @NonNull Supplier<ListenableFuture<MediaBrowser>> mediaBrowserListenableFuture,
            @NonNull Function<Integer, Child> itemAt) {

        ItemTouchHelper previous = ATTACHED.remove(recyclerView);
        if (previous != null) previous.attachToRecyclerView(null);

        ItemTouchHelper helper = new ItemTouchHelper(new ItemTouchHelper.SimpleCallback(0, ItemTouchHelper.RIGHT) {
            @Override
            public boolean onMove(@NonNull RecyclerView recyclerView, @NonNull RecyclerView.ViewHolder viewHolder, @NonNull RecyclerView.ViewHolder target) {
                return false;
            }

            @Override
            public void onChildDraw(@NonNull Canvas c, @NonNull RecyclerView recyclerView, @NonNull RecyclerView.ViewHolder viewHolder, float dX, float dY, int actionState, boolean isCurrentlyActive) {
                if (actionState == ItemTouchHelper.ACTION_STATE_SWIPE) {
                    drawSwipeAction(c, viewHolder, dX,
                            ContextCompat.getColor(viewHolder.itemView.getContext(), R.color.swipeQueueBackground),
                            ContextCompat.getDrawable(viewHolder.itemView.getContext(), R.drawable.ic_queue_white));
                }
                super.onChildDraw(c, recyclerView, viewHolder, dX, dY, actionState, isCurrentlyActive);
            }

            @Override
            public void onSwiped(@NonNull RecyclerView.ViewHolder viewHolder, int direction) {
                int position = viewHolder.getBindingAdapterPosition();
                RecyclerView.Adapter<?> adapter = recyclerView.getAdapter();

                // The view holder may still reference a freshly recreated adapter whose differ has
                // not populated yet (or one that was replaced entirely). Never index out of bounds.
                Child song = null;
                if (adapter != null && position != RecyclerView.NO_POSITION
                        && position >= 0 && position < adapter.getItemCount()) {
                    song = itemAt.apply(position);
                }

                if (song != null && !song.isDir()) {
                    MediaManager.enqueue(mediaBrowserListenableFuture.get(), song, true, true);
                    Toast.makeText(recyclerView.getContext(), R.string.swipe_play_next_toast, Toast.LENGTH_SHORT).show();
                }

                if (adapter != null && position != RecyclerView.NO_POSITION
                        && position >= 0 && position < adapter.getItemCount()) {
                    adapter.notifyItemChanged(position);
                }
            }
        });

        ATTACHED.put(recyclerView, helper);
        helper.attachToRecyclerView(recyclerView);
    }

    // Paints the swipe-action affordance behind a row that is being slid: a filled background on
    // the revealed side plus an icon at the edge of the row. dX > 0 means the row slides right,
    // revealing space on its left (icon near the left edge); dX < 0 reveals space on the right.
    public static void drawSwipeAction(
            @NonNull Canvas canvas,
            @NonNull RecyclerView.ViewHolder viewHolder,
            float dX,
            int backgroundColor,
            Drawable icon) {

        android.view.View itemView = viewHolder.itemView;
        if (dX == 0 || icon == null) return;

        float left, right;
        if (dX > 0) {
            left = itemView.getLeft();
            right = itemView.getLeft() + dX;
        } else {
            left = itemView.getRight() + dX;
            right = itemView.getRight();
        }

        Paint paint = new Paint();
        paint.setColor(backgroundColor);
        canvas.drawRect(left, itemView.getTop(), right, itemView.getBottom(), paint);

        float density = itemView.getResources().getDisplayMetrics().density;
        float iconSize = 24 * density;
        float iconTop = itemView.getTop() + (itemView.getHeight() - iconSize) / 2f;
        float iconLeft;
        if (dX > 0) {
            iconLeft = itemView.getLeft() + 20 * density;
        } else {
            iconLeft = itemView.getRight() - 20 * density - iconSize;
        }
        icon.setBounds((int) iconLeft, (int) iconTop, (int) (iconLeft + iconSize), (int) (iconTop + iconSize));
        icon.draw(canvas);
    }
}
